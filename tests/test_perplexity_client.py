"""
Unit tests for Perplexity API client.

Tests retry logic, exponential backoff with jitter,
rate limit handling, and timeout scenarios.
"""

import pytest
import time
from unittest.mock import patch, MagicMock, Mock
from http import HTTPStatus
import httpx
import openai
from src.perplexity_client import PerplexityClient


def _create_openai_error(error_class, message: str, status_code: int, headers=None):
    """Helper to create OpenAI errors with required response/body args."""
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.headers = headers or {}
    error = error_class(message, response=mock_response, body=None)
    return error
import openai
from src.perplexity_client import PerplexityClient


@pytest.mark.unit
class TestPerplexityClient:
    """Test suite for PerplexityClient retry and error handling."""
    
    def test_chat_success(self, test_settings):
        """Test successful API call without retries."""
        client = PerplexityClient(test_settings)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"result": "success"}'
        
        with patch.object(client.client.chat.completions, 'create', return_value=mock_response):
            result = client.chat([{"role": "user", "content": "test"}])
        
        assert result == '{"result": "success"}'
    
    def test_chat_rate_limit_retry(self, test_settings):
        """Test retry on rate limit error (429)."""
        client = PerplexityClient(test_settings)
        
        # First call raises RateLimitError, second succeeds
        rate_limit_error = _create_openai_error(openai.RateLimitError, "Rate limit exceeded", 429)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "success"
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise rate_limit_error
            return mock_response
        
        with patch.object(client.client.chat.completions, 'create', side_effect=side_effect):
            with patch('time.sleep'):  # Skip actual sleep
                result = client.chat([{"role": "user", "content": "test"}])
        
        assert result == "success"
        assert call_count[0] == 2  # Retried once
    
    def test_chat_server_error_retry(self, test_settings):
        """Test retry on 5xx server error."""
        client = PerplexityClient(test_settings)
        
        # First call raises 503, second succeeds
        server_error = _create_openai_error(openai.InternalServerError, "Service unavailable", 503)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "success"
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise server_error
            return mock_response
        
        with patch.object(client.client.chat.completions, 'create', side_effect=side_effect):
            with patch('time.sleep'):
                result = client.chat([{"role": "user", "content": "test"}])
        
        assert result == "success"
        assert call_count[0] == 2
    
    def test_chat_timeout_retry(self, test_settings):
        """Test retry on timeout error."""
        client = PerplexityClient(test_settings)
        
        timeout_error = openai.APITimeoutError("Request timeout")
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "success"
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise timeout_error
            return mock_response
        
        with patch.object(client.client.chat.completions, 'create', side_effect=side_effect):
            with patch('time.sleep'):
                result = client.chat([{"role": "user", "content": "test"}])
        
        assert result == "success"
        assert call_count[0] == 2
    
    def test_chat_max_retries_exceeded(self, test_settings):
        """Test failure after max retries exhausted."""
        client = PerplexityClient(test_settings)
        
        rate_limit_error = _create_openai_error(openai.RateLimitError, "Rate limit exceeded", 429)
        
        with patch.object(client.client.chat.completions, 'create', side_effect=rate_limit_error):
            with patch('time.sleep'):
                with pytest.raises(openai.RateLimitError):
                    client.chat([{"role": "user", "content": "test"}])
    
    def test_chat_non_retryable_error(self, test_settings):
        """Test that 4xx errors (except 429) are not retried."""
        client = PerplexityClient(test_settings)
        
        # 400 Bad Request should not retry
        bad_request = openai.APIStatusError("Bad request", response=MagicMock(), body=None)
        bad_request.status_code = 400
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            raise bad_request
        
        with patch.object(client.client.chat.completions, 'create', side_effect=side_effect):
            with pytest.raises(openai.APIStatusError):
                client.chat([{"role": "user", "content": "test"}])
        
        # Should fail immediately without retry
        assert call_count[0] == 1
    
    def test_chat_retry_after_header(self, test_settings):
        """Test that Retry-After header is respected."""
        client = PerplexityClient(test_settings)
        
        # Create rate limit error with Retry-After header
        rate_limit_error = _create_openai_error(
            openai.RateLimitError, 
            "Rate limit exceeded", 
            429, 
            headers={'Retry-After': '5.0'}
        )
        
        mock_success = MagicMock()
        mock_success.choices = [MagicMock()]
        mock_success.choices[0].message.content = "success"
        
        call_count = [0]
        sleep_duration = [0]
        
        def mock_sleep(duration):
            sleep_duration[0] = duration
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise rate_limit_error
            return mock_success
        
        with patch.object(client.client.chat.completions, 'create', side_effect=side_effect):
            with patch('time.sleep', side_effect=mock_sleep):
                result = client.chat([{"role": "user", "content": "test"}])
        
        assert result == "success"
        # Should use Retry-After value (5.0) instead of backoff calculation
        assert sleep_duration[0] == 5.0
    
    def test_chat_exponential_backoff(self, test_settings):
        """Test exponential backoff progression."""
        client = PerplexityClient(test_settings)
        
        rate_limit_error = _create_openai_error(openai.RateLimitError, "Rate limit", 429)
        
        sleep_durations = []
        
        def mock_sleep(duration):
            sleep_durations.append(duration)
        
        with patch.object(client.client.chat.completions, 'create', side_effect=rate_limit_error):
            with patch('time.sleep', side_effect=mock_sleep):
                with pytest.raises(openai.RateLimitError):
                    client.chat([{"role": "user", "content": "test"}])
        
        # Should have 3 retries (4 total attempts)
        assert len(sleep_durations) == 3
        
        # Check that backoff increases (with jitter, approximate check)
        # Initial backoff = 2s, then 4s, then 8s (with ±25% jitter)
        assert 1.5 <= sleep_durations[0] <= 2.5  # 2s ± 25%
        assert 3.0 <= sleep_durations[1] <= 5.0  # 4s ± 25%
        assert 6.0 <= sleep_durations[2] <= 10.0  # 8s ± 25%
    
    def test_chat_jitter_applied(self, test_settings):
        """Test that jitter is applied to backoff delays."""
        client = PerplexityClient(test_settings)
        
        rate_limit_error = _create_openai_error(openai.RateLimitError, "Rate limit", 429)
        
        sleep_duration = [0]
        
        def mock_sleep(duration):
            sleep_duration[0] = duration
        
        call_count = [0]
        mock_success = MagicMock()
        mock_success.choices = [MagicMock()]
        mock_success.choices[0].message.content = "success"
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise rate_limit_error
            return mock_success
        
        with patch.object(client.client.chat.completions, 'create', side_effect=side_effect):
            with patch('time.sleep', side_effect=mock_sleep):
                client.chat([{"role": "user", "content": "test"}])
        
        # Sleep duration should be 2s * jitter (0.75-1.25)
        # Not exactly 2.0 (which would indicate no jitter)
        assert sleep_duration[0] != 2.0
        assert 1.5 <= sleep_duration[0] <= 2.5
    
    @pytest.mark.skip(reason="budget_tracker module not yet implemented (Issue 18 pending)")
    def test_chat_budget_exceeded_no_retry(self, test_settings):
        """Test that BudgetExceededError is not retried."""
        # from src.budget_tracker import BudgetExceededError
        pass
        pass
    
    def test_chat_custom_model(self, test_settings):
        """Test chat with custom model parameter."""
        client = PerplexityClient(test_settings)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "success"
        
        with patch.object(client.client.chat.completions, 'create', return_value=mock_response) as mock_create:
            client.chat([{"role": "user", "content": "test"}], model="pplx-70b-online")
        
        # Verify custom model was passed
        mock_create.assert_called_once()
        assert mock_create.call_args[1]['model'] == "pplx-70b-online"
    
    def test_chat_custom_temperature(self, test_settings):
        """Test chat with custom temperature parameter."""
        client = PerplexityClient(test_settings)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "success"
        
        with patch.object(client.client.chat.completions, 'create', return_value=mock_response) as mock_create:
            client.chat([{"role": "user", "content": "test"}], temperature=0.5)
        
        # Verify custom temperature was passed
        assert mock_create.call_args[1]['temperature'] == 0.5

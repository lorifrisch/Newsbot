"""
Unit tests for mailer module.

Tests email sending with SendGrid, retry logic with exponential
backoff, template rendering, and error handling.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.mailer import NewsMailer


@pytest.mark.unit
class TestNewsMailer:
    """Test suite for NewsMailer class."""
    
    def test_render_content_success(self, test_settings):
        """Test successful template rendering."""
        mailer = NewsMailer(test_settings)
        
        context = {
            "headline": "Test Headline",
            "intro": "Test intro paragraph"
        }
        
        # Mock template
        mock_template = MagicMock()
        mock_template.render.return_value = "<html>Test Email</html>"
        
        with patch.object(mailer.jinja_env, 'get_template', return_value=mock_template):
            result = mailer.render_content("email_template.html", context)
        
        assert result == "<html>Test Email</html>"
        # Should add brand_name to context
        mock_template.render.assert_called_once()
        call_context = mock_template.render.call_args[1]
        assert "brand_name" in call_context
    
    def test_render_content_missing_template(self, test_settings):
        """Test error handling for missing template."""
        mailer = NewsMailer(test_settings)
        
        with patch.object(mailer.jinja_env, 'get_template', side_effect=Exception("Template not found")):
            with pytest.raises(Exception):
                mailer.render_content("nonexistent.html", {})
    
    def test_send_email_success(self, test_settings, mock_sendgrid_client):
        """Test successful email sending without retries."""
        mailer = NewsMailer(test_settings)
        mailer.sg_client = mock_sendgrid_client
        
        result = mailer.send_email(
            subject="Test Subject",
            html_content="<html>Test</html>"
        )
        
        assert result is True
        mock_sendgrid_client.send.assert_called_once()
    
    def test_send_email_with_subject_prefix(self, test_settings, mock_sendgrid_client):
        """Test that subject prefix is added."""
        mailer = NewsMailer(test_settings)
        mailer.sg_client = mock_sendgrid_client
        
        mailer.send_email(
            subject="Daily Brief",
            html_content="<html>Test</html>"
        )
        
        # Verify subject includes prefix
        call_args = mock_sendgrid_client.send.call_args
        message = call_args[0][0]
        assert test_settings.email.subject_prefix in message.subject.get()
    
    def test_send_email_rate_limit_retry(self, test_settings):
        """Test retry on rate limit (429) error."""
        mailer = NewsMailer(test_settings)
        
        # First call returns 429, second succeeds
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.body = "Rate limit"
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 202
        mock_response_success.body = "Accepted"
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response_429
            return mock_response_success
        
        mock_client = MagicMock()
        mock_client.send.side_effect = side_effect
        mailer.sg_client = mock_client
        
        with patch('time.sleep'):  # Skip actual sleep
            result = mailer.send_email("Test", "<html>Test</html>")
        
        assert result is True
        assert call_count[0] == 2  # Retried once
    
    def test_send_email_server_error_retry(self, test_settings):
        """Test retry on 5xx server error."""
        mailer = NewsMailer(test_settings)
        
        # First call returns 503, second succeeds
        mock_response_503 = MagicMock()
        mock_response_503.status_code = 503
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 202
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response_503
            return mock_response_success
        
        mock_client = MagicMock()
        mock_client.send.side_effect = side_effect
        mailer.sg_client = mock_client
        
        with patch('time.sleep'):
            result = mailer.send_email("Test", "<html>Test</html>")
        
        assert result is True
        assert call_count[0] == 2
    
    def test_send_email_max_retries_exceeded(self, test_settings):
        """Test failure after max retries exhausted."""
        mailer = NewsMailer(test_settings)
        
        mock_response = MagicMock()
        mock_response.status_code = 503
        
        mock_client = MagicMock()
        mock_client.send.return_value = mock_response
        mailer.sg_client = mock_client
        
        with patch('time.sleep'):
            result = mailer.send_email("Test", "<html>Test</html>")
        
        assert result is False
        # Should attempt 4 times (1 initial + 3 retries)
        assert mock_client.send.call_count == 4
    
    def test_send_email_client_error_no_retry(self, test_settings):
        """Test that 4xx client errors (except 429) are not retried."""
        mailer = NewsMailer(test_settings)
        
        mock_response = MagicMock()
        mock_response.status_code = 400  # Bad request
        mock_response.body = "Bad request"
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return mock_response
        
        mock_client = MagicMock()
        mock_client.send.side_effect = side_effect
        mailer.sg_client = mock_client
        
        result = mailer.send_email("Test", "<html>Test</html>")
        
        assert result is False
        # Should not retry on 4xx (except 429)
        assert call_count[0] == 1
    
    def test_send_email_exception_retry(self, test_settings):
        """Test retry on network exceptions."""
        mailer = NewsMailer(test_settings)
        
        # First call raises exception, second succeeds
        mock_response_success = MagicMock()
        mock_response_success.status_code = 202
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Network error")
            return mock_response_success
        
        mock_client = MagicMock()
        mock_client.send.side_effect = side_effect
        mailer.sg_client = mock_client
        
        with patch('time.sleep'):
            result = mailer.send_email("Test", "<html>Test</html>")
        
        assert result is True
        assert call_count[0] == 2
    
    def test_send_email_exponential_backoff(self, test_settings):
        """Test exponential backoff progression."""
        mailer = NewsMailer(test_settings)
        
        mock_response = MagicMock()
        mock_response.status_code = 503
        
        mock_client = MagicMock()
        mock_client.send.return_value = mock_response
        mailer.sg_client = mock_client
        
        sleep_durations = []
        def mock_sleep(duration):
            sleep_durations.append(duration)
        
        with patch('time.sleep', side_effect=mock_sleep):
            mailer.send_email("Test", "<html>Test</html>")
        
        # Should have 3 retries
        assert len(sleep_durations) == 3
        
        # Check exponential backoff with jitter
        # Initial: 2s, then 4s, then 8s (with ±25% jitter)
        assert 1.5 <= sleep_durations[0] <= 2.5
        assert 3.0 <= sleep_durations[1] <= 5.0
        assert 6.0 <= sleep_durations[2] <= 10.0
    
    def test_send_email_jitter_applied(self, test_settings):
        """Test that jitter is applied to backoff delays."""
        mailer = NewsMailer(test_settings)
        
        mock_response_503 = MagicMock()
        mock_response_503.status_code = 503
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 202
        
        sleep_duration = [0]
        def mock_sleep(duration):
            sleep_duration[0] = duration
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response_503
            return mock_response_success
        
        mock_client = MagicMock()
        mock_client.send.side_effect = side_effect
        mailer.sg_client = mock_client
        
        with patch('time.sleep', side_effect=mock_sleep):
            mailer.send_email("Test", "<html>Test</html>")
        
        # Jitter should make it not exactly 2.0
        assert sleep_duration[0] != 2.0
        assert 1.5 <= sleep_duration[0] <= 2.5
    
    def test_send_email_custom_recipients(self, test_settings, mock_sendgrid_client):
        """Test sending email with custom from/to addresses."""
        mailer = NewsMailer(test_settings)
        mailer.sg_client = mock_sendgrid_client
        
        mailer.send_email(
            subject="Test",
            html_content="<html>Test</html>",
            from_email="custom-from@example.com",
            to_email="custom-to@example.com"
        )
        
        call_args = mock_sendgrid_client.send.call_args
        message = call_args[0][0]
        
        # Verify custom addresses were used
        assert message.from_email.email == "custom-from@example.com"
        # to_emails is a list of Personalization objects, check first one
        assert any("custom-to@example.com" in str(p.tos) for p in message.personalizations)
    
    def test_send_email_default_recipients(self, test_settings, mock_sendgrid_client):
        """Test that default recipients are used when not specified."""
        mailer = NewsMailer(test_settings)
        mailer.sg_client = mock_sendgrid_client
        
        mailer.send_email(
            subject="Test",
            html_content="<html>Test</html>"
        )
        
        call_args = mock_sendgrid_client.send.call_args
        message = call_args[0][0]
        
        # Should use config defaults
        assert message.from_email.email == test_settings.email.from_email
        assert any(test_settings.email.to_email in str(p.tos) for p in message.personalizations)

import pytest
from unittest.mock import MagicMock, patch
from src.openai_client import OpenAIClient
from src.config import Settings

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.openai_api_key.get_secret_value.return_value = "fake-key"
    settings.models.extract_model = "gpt-5-mini"
    settings.models.write_model = "gpt-5-mini"
    settings.models.fallback_model = "gpt-4o-mini"
    return settings

def test_openai_client_initialization(mock_settings):
    client = OpenAIClient(mock_settings)
    assert client.extract_model == "gpt-5-mini"
    assert client.write_model == "gpt-5-mini"
    assert client.fallback == "gpt-4o-mini"

@patch("openai.resources.chat.completions.Completions.create")
def test_responses_create_success(mock_create, mock_settings):
    client = OpenAIClient(mock_settings)
    
    # Mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"result": "ok"}'))]
    mock_response.usage = MagicMock(total_tokens=10, prompt_tokens=5, completion_tokens=5)
    mock_create.return_value = mock_response
    
    messages = [{"role": "user", "content": "hello"}]
    res = client.responses_create(messages, model_type="write", max_output_tokens=100)
    
    assert res.choices[0].message.content == '{"result": "ok"}'
    # Verify correct model was passed
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert kwargs["model"] == "gpt-5-mini"
    assert kwargs["max_tokens"] == 100

@patch("openai.resources.chat.completions.Completions.create")
def test_responses_create_retry_and_fallback(mock_create, mock_settings):
    client = OpenAIClient(mock_settings)
    
    # Mock failure then success
    import openai
    mock_create.side_effect = [
        openai.RateLimitError("Rate limit", response=MagicMock(), body=None),
        MagicMock(choices=[MagicMock(message=MagicMock(content='{"result": "fallback_ok"}'))], 
                 usage=MagicMock(total_tokens=10, prompt_tokens=5, completion_tokens=5))
    ]
    
    # Patch time.sleep to speed up test
    with patch("time.sleep", return_value=None):
        messages = [{"role": "user", "content": "hello"}]
        res = client.responses_create(messages, model_type="extract")
        
    assert res.choices[0].message.content == '{"result": "fallback_ok"}'
    assert mock_create.call_count == 2
    
    # Second call should use fallback model
    args, kwargs = mock_create.call_args_list[1]
    assert kwargs["model"] == "gpt-4o-mini"

import pytest
import os
from unittest.mock import patch, mock_open
from src.config import Settings, AppConfig

@pytest.fixture
def mock_env():
    return {
        "OPENAI_API_KEY": "sk-test-openai",
        "PERPLEXITY_API_KEY": "pplx-test-perplexity",
        "SENDGRID_API_KEY": "SG-test-sendgrid",
        "EMAIL_FROM": "from@example.com",
        "EMAIL_TO": "to@example.com",
    }

@pytest.fixture
def mock_yaml():
    return """
app:
  name: "Custom Name"
watchlist:
  tickers: ["BTC", "ETH"]
coverage:
  us: 0.5
"""

def test_load_settings_success(mock_env, mock_yaml):
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("builtins.open", mock_open(read_data=mock_yaml)):
            with patch("pathlib.Path.exists", return_value=True):
                settings = Settings.load()
                assert settings.app.name == "Custom Name"
                assert settings.openai_api_key.get_secret_value() == "sk-test-openai"
                assert settings.watchlist_tickers == ["BTC", "ETH"]
                assert settings.coverage["us"] == 0.5

def test_load_settings_missing_env(mock_env):
    # Settings.load() doesn't enforce required fields, it allows None values
    # Remove an API key
    del mock_env["OPENAI_API_KEY"]
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("pathlib.Path.exists", return_value=False):
            settings = Settings.load()
            # It loads successfully, but the key will be None (masked as SecretStr)
            assert settings.openai_api_key is not None  # SecretStr wraps None

def test_legacy_email_mapping():
    legacy_env = {
        "OPENAI_API_KEY": "sk-test",
        "PERPLEXITY_API_KEY": "pplx-test",
        "SENDGRID_API_KEY": "SG-test",
        "SENDGRID_FROM_EMAIL": "legacy_from@example.com",
        "RECIPIENT_EMAIL": "legacy_to@example.com",
    }
    with patch.dict(os.environ, legacy_env, clear=True):
        with patch("pathlib.Path.exists", return_value=False):
            settings = Settings.load()
            assert settings.email.from_email == "legacy_from@example.com"
            assert settings.email.to_email == "legacy_to@example.com"

def test_config_yaml_path_override(mock_env):
    mock_env["CONFIG_YAML_PATH"] = "custom_config.yaml"
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="app: {name: 'Overridden'}")) as mock_file:
                settings = Settings.load()
                assert settings.app.name == "Overridden"


# Additional edge case tests
@pytest.mark.unit
def test_invalid_email_format(mock_env, mock_yaml):
    """Test that Settings.load accepts any string for email (no validation at load time)."""
    mock_env["EMAIL_FROM"] = "not-an-email"
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("builtins.open", mock_open(read_data=mock_yaml)):
            with patch("pathlib.Path.exists", return_value=True):
                # Pydantic BaseSettings doesn't validate email format, it just accepts strings
                settings = Settings.load()
                assert settings.email.from_email == "not-an-email"


@pytest.mark.unit
def test_empty_watchlist_tickers(mock_env):
    """Test configuration with empty watchlist."""
    yaml_content = """
app:
  name: "Test"
watchlist:
  tickers: []
"""
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("pathlib.Path.exists", return_value=True):
                settings = Settings.load()
                assert settings.watchlist_tickers == []


@pytest.mark.unit
def test_malformed_yaml(mock_env):
    """Test handling of malformed YAML."""
    malformed_yaml = "app:\n  name: Test\n  - invalid: yaml"
    
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("builtins.open", mock_open(read_data=malformed_yaml)):
            with patch("pathlib.Path.exists", return_value=True):
                with pytest.raises(Exception):  # YAML parsing error
                    Settings.load()


@pytest.mark.unit
def test_missing_config_file_uses_defaults(mock_env):
    """Test that missing config.yaml falls back to defaults."""
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("pathlib.Path.exists", return_value=False):
            settings = Settings.load()
            # Should use default values
            assert settings.app.name == "Markets News Brief"
            assert settings.app.log_level == "INFO"


@pytest.mark.unit
def test_partial_yaml_config(mock_env):
    """Test YAML with only some sections defined."""
    partial_yaml = """
app:
  name: "Partial Config"
"""
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("builtins.open", mock_open(read_data=partial_yaml)):
            with patch("pathlib.Path.exists", return_value=True):
                settings = Settings.load()
                assert settings.app.name == "Partial Config"
                assert settings.app.brand_name == "Smart Invest"  # Default
                # No default tickers - empty list if not in YAML
                assert settings.watchlist_tickers == []


@pytest.mark.unit
def test_unicode_in_config(mock_env):
    """Test handling of unicode characters in config."""
    unicode_yaml = """
app:
  name: "Markets Briefing 📈"
  brand_name: "Smart Invest™"
"""
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("builtins.open", mock_open(read_data=unicode_yaml)):
            with patch("pathlib.Path.exists", return_value=True):
                settings = Settings.load()
                assert "📈" in settings.app.name
                assert "™" in settings.app.brand_name


@pytest.mark.unit
def test_secret_str_masking(mock_env, mock_yaml):
    """Test that SecretStr properly masks sensitive data."""
    with patch.dict(os.environ, mock_env, clear=True):
        with patch("builtins.open", mock_open(read_data=mock_yaml)):
            with patch("pathlib.Path.exists", return_value=True):
                settings = Settings.load()
                # Verify secret is masked in repr
                assert "sk-test-openai" not in repr(settings.openai_api_key)
                # But accessible via get_secret_value()
                assert settings.openai_api_key.get_secret_value() == "sk-test-openai"


from .config import settings

def load_config():
    """Deprecated: Use src.config.settings instead."""
    return {
        "app": settings.app.model_dump(),
        "coverage": settings.coverage,
        "watchlist": {"tickers": settings.watchlist_tickers},
        "models": settings.models.model_dump(),
        "email": settings.email.model_dump()
    }

def load_env():
    """Deprecated: Use src.config.settings instead."""
    return {
        "OPENAI_API_KEY": settings.openai_api_key.get_secret_value(),
        "PERPLEXITY_API_KEY": settings.perplexity_api_key.get_secret_value(),
        "SENDGRID_API_KEY": settings.email.api_key.get_secret_value(),
        "SENDGRID_FROM_EMAIL": settings.email.from_email,
        "RECIPIENT_EMAIL": settings.email.to_email,
        "DATABASE_PATH": settings.database_path,
    }

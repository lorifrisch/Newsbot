import os
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load env vars before defining settings to allow env-based overrides
load_dotenv()

class AppConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = "Markets News Brief"
    brand_name: str = "Smart Invest"
    log_level: str = "INFO"

class ModelConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    retrieval: str = "sonar"
    # Mapping extraction and composition from YAML
    extract_model: str = Field("gpt-4o", validation_alias="extraction")
    write_model: str = Field("gpt-4o", validation_alias="composition")
    fallback_model: str = "gpt-4o-mini"
    # Token caps
    extraction_max_tokens: int = 3000
    composition_max_tokens: int = 2048
    weekly_composition_max_tokens: int = 3000
    # Use strict JSON schema for extraction
    use_strict_schema: bool = True

class DailyConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    snippet_words: int = 80
    max_candidates: int = 50
    max_candidates_per_query: int = 8
    max_clusters: int = 14  # For fact-card extraction
    # Regional minimums
    min_us_items: int = 25
    min_eu_items: int = 8
    min_china_items: int = 4
    # Watchlist settings
    min_watchlist_tickers_covered: int = 5
    max_items_per_ticker: int = 2

class SentimentBoostRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    min: float = 0.95
    max: float = 1.15

class RankingConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    use_sentiment_boost: bool = True
    sentiment_boost_range: SentimentBoostRange = Field(default_factory=SentimentBoostRange)
    # Coverage constraints
    require_us_in_top5: bool = True
    require_eu_in_top5: bool = True
    require_china_in_top5: bool = True
    # Filtering
    deprioritize_analyst_targets: bool = True
    analyst_target_keywords: List[str] = Field(default_factory=lambda: [
        "price target", "analyst rating", "upgraded", "downgraded", "initiated coverage"
    ])

class MarketDataConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    use_real_data: bool = True
    snapshot_assets: List[str] = Field(default_factory=lambda: [
        "S&P 500", "Nasdaq", "Stoxx 600", "US 10Y Yield",
        "EUR/USD", "USD/JPY", "Brent Oil", "VIX", "Bitcoin"
    ])

class RetrievalConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    allowed_domains: List[str] = Field(default_factory=list)  # Empty = allow all

class EmailConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    sender: str = "noreply@smartinvest.com"
    subject_prefix: str = "[Markets Brief]"
    weekly_subject_prefix: str = "[Weekly Recap]"
    api_key: SecretStr = Field(..., validation_alias="SENDGRID_API_KEY")
    from_email: str = Field(..., validation_alias="EMAIL_FROM")
    to_email: str = Field(..., validation_alias="EMAIL_TO")
    # Chart embedding method: "base64" (inline) or "cid" (attachment, more reliable)
    chart_embed_method: str = "cid"

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_email_vars(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map legacy names if new ones aren't present
            if "EMAIL_FROM" not in os.environ and "SENDGRID_FROM_EMAIL" in os.environ:
                data["EMAIL_FROM"] = os.environ["SENDGRID_FROM_EMAIL"]
            if "EMAIL_TO" not in os.environ and "RECIPIENT_EMAIL" in os.environ:
                data["EMAIL_TO"] = os.environ["RECIPIENT_EMAIL"]
        return data

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

    app: AppConfig = Field(default_factory=AppConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    email: EmailConfig
    daily: DailyConfig = Field(default_factory=DailyConfig)
    ranking: RankingConfig = Field(default_factory=RankingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    
    openai_api_key: SecretStr = Field(..., validation_alias="OPENAI_API_KEY")
    perplexity_api_key: SecretStr = Field(..., validation_alias="PERPLEXITY_API_KEY")
    database_path: str = Field("data/news_workflow.db", validation_alias="DATABASE_PATH")
    
    watchlist_tickers: List[str] = []
    coverage: Dict[str, float] = {}

    @classmethod
    def load(cls) -> "Settings":
        # 1. Determine config path
        config_path_str = os.getenv("CONFIG_YAML_PATH", "config.yaml")
        config_path = Path(config_path_str)
        
        yaml_config = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                yaml_config = yaml.safe_load(f) or {}
        
        # 2. Extract nested configs from YAML if present
        # We merge YAML data into the constructor
        # Env vars will override these due to Pydantic Settings behavior
        
        # Flatten watchlist for easier mapping if needed, 
        # but here we'll just pull from YAML mapping
        watchlist = yaml_config.get("watchlist", {}).get("tickers", [])
        coverage = yaml_config.get("coverage", {})
        
        # Build ranking config with nested sentiment_boost_range
        ranking_yaml = yaml_config.get("ranking", {})
        ranking_config = RankingConfig(
            use_sentiment_boost=ranking_yaml.get("use_sentiment_boost", True),
            sentiment_boost_range=SentimentBoostRange(**ranking_yaml.get("sentiment_boost_range", {})),
            require_us_in_top5=ranking_yaml.get("require_us_in_top5", True),
            require_eu_in_top5=ranking_yaml.get("require_eu_in_top5", True),
            require_china_in_top5=ranking_yaml.get("require_china_in_top5", True),
            deprioritize_analyst_targets=ranking_yaml.get("deprioritize_analyst_targets", True),
            analyst_target_keywords=ranking_yaml.get("analyst_target_keywords", [
                "price target", "analyst rating", "upgraded", "downgraded", "initiated coverage"
            ])
        )
        
        # Build retrieval config
        retrieval_yaml = yaml_config.get("retrieval", {})
        retrieval_config = RetrievalConfig(**retrieval_yaml)
        
        # Build market data config
        market_data_yaml = yaml_config.get("market_data", {})
        market_data_config = MarketDataConfig(**market_data_yaml)
        
        # Initialize Settings. 
        # Note: Pydantic BaseSettings automatically pulls from environment variables 
        # for fields defined with validation_alias or matching field names.
        try:
            return cls(
                app=AppConfig(**yaml_config.get("app", {})),
                models=ModelConfig(**yaml_config.get("models", {})),
                daily=DailyConfig(**yaml_config.get("daily", {})),
                ranking=ranking_config,
                retrieval=retrieval_config,
                market_data=market_data_config,
                email=EmailConfig(
                    **yaml_config.get("email", {}),
                    # These will be overridden by env vars anyway if present
                    api_key=os.getenv("SENDGRID_API_KEY"),
                    from_email=os.getenv("EMAIL_FROM") or os.getenv("SENDGRID_FROM_EMAIL"),
                    to_email=os.getenv("EMAIL_TO") or os.getenv("RECIPIENT_EMAIL")
                ),
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                perplexity_api_key=os.getenv("PERPLEXITY_API_KEY"),
                database_path=os.getenv("DATABASE_PATH", "data/news_workflow.db"),
                watchlist_tickers=watchlist,
                coverage=coverage
            )
        except Exception as e:
            # Raise a clear error as requested
            raise RuntimeError(f"Failed to load settings: {e}")

# Export a function to get settings for better testability
def get_settings() -> Settings:
    return Settings.load()

# Global settings instance - note that this will call load() on import.
# In a real app, you might want to wrap this in a try/except or handle it in main.py.
try:
    settings = get_settings()
except Exception:
    # We allow the instance to be None if it fails during module import (e.g. in some test scenarios)
    # but the app should rely on get_settings() or check if settings is None.
    settings = None

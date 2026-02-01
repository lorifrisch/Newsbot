"""
Shared pytest fixtures for all tests.

Provides reusable fixtures for mock environments, test settings,
temporary databases, and sample data objects.
"""

import os
import json
import tempfile
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from typing import Dict, List

from src.config import Settings
from src.retrieval import MarketNewsItem
from src.clustering import StoryCluster
from src.extract import FactCard


@pytest.fixture
def mock_env() -> Dict[str, str]:
    """
    Mock environment variables for testing.
    Provides valid API keys and configuration.
    """
    return {
        "OPENAI_API_KEY": "sk-test-key-1234567890abcdef",
        "PERPLEXITY_API_KEY": "pplx-test-key-abcdef123456",
        "SENDGRID_API_KEY": "SG.test-key-xyz789",
        "EMAIL_FROM": "test@example.com",
        "EMAIL_TO": "recipient@example.com",
    }


@pytest.fixture
def test_settings(mock_env, tmp_path):
    """
    Load Settings with mocked environment variables.
    Uses temporary database path.
    """
    mock_env["DATABASE_PATH"] = str(tmp_path / "test.db")
    
    with patch.dict(os.environ, mock_env, clear=True):
        settings = Settings.load()
    
    return settings


@pytest.fixture
def temp_db(tmp_path):
    """
    Create a temporary SQLite database for testing.
    Returns path to database file.
    """
    db_path = tmp_path / "test_news.db"
    return str(db_path)


@pytest.fixture
def temp_run_dir(tmp_path):
    """
    Create a temporary run directory for artifacts.
    """
    run_dir = tmp_path / "test_run"
    run_dir.mkdir(exist_ok=True)
    return run_dir


@pytest.fixture
def sample_news_items() -> List[Dict]:
    """
    Sample news items in Perplexity response format.
    Covers multiple regions and sources.
    """
    return [
        {
            "title": "Fed Signals Rate Pause Amid Cooling Inflation",
            "source": "Reuters",
            "url": "https://reuters.com/markets/fed-pause-2026-01",
            "published_at": "2026-01-31T10:00:00Z",
            "snippet": "Federal Reserve officials indicated they may pause rate hikes as inflation shows signs of cooling to their 2% target.",
            "region": "us"
        },
        {
            "title": "Tech Stocks Rally on Strong Earnings",
            "source": "Bloomberg",
            "url": "https://bloomberg.com/tech/earnings-rally-2026",
            "published_at": "2026-01-31T09:30:00Z",
            "snippet": "Major tech companies reported better-than-expected quarterly earnings, driving a broad market rally.",
            "region": "us"
        },
        {
            "title": "ECB Maintains Hawkish Stance Despite Slowdown",
            "source": "Financial Times",
            "url": "https://ft.com/ecb-policy-2026-01",
            "published_at": "2026-01-31T08:00:00Z",
            "snippet": "European Central Bank kept rates unchanged but signaled continued vigilance on inflation risks.",
            "region": "eu"
        },
        {
            "title": "China Property Sector Shows Signs of Stabilization",
            "source": "South China Morning Post",
            "url": "https://scmp.com/china/property-stabilize",
            "published_at": "2026-01-31T07:00:00Z",
            "snippet": "Government stimulus measures appear to be supporting property markets in major cities.",
            "region": "china"
        },
        {
            "title": "NVIDIA Earnings Beat Estimates on AI Demand",
            "source": "CNBC",
            "url": "https://cnbc.com/nvda-earnings-2026-q4",
            "published_at": "2026-01-30T21:00:00Z",
            "snippet": "NVIDIA reported record revenue driven by strong demand for AI chips from data centers.",
            "region": "us"
        }
    ]


@pytest.fixture
def sample_market_news_items(sample_news_items) -> List[MarketNewsItem]:
    """
    Convert sample news items to MarketNewsItem objects.
    """
    return [MarketNewsItem(**item) for item in sample_news_items]


@pytest.fixture
def sample_clusters(sample_market_news_items) -> List[StoryCluster]:
    """
    Sample story clusters for testing.
    3 clusters with varying support items.
    """
    return [
        StoryCluster(
            primary_item=sample_market_news_items[0],
            supporting_items=[],
            cluster_id="cluster_fed_pause"
        ),
        StoryCluster(
            primary_item=sample_market_news_items[1],
            supporting_items=[sample_market_news_items[4]],  # NVDA supports tech rally
            cluster_id="cluster_tech_rally"
        ),
        StoryCluster(
            primary_item=sample_market_news_items[2],
            supporting_items=[],
            cluster_id="cluster_ecb"
        )
    ]


@pytest.fixture
def sample_fact_cards() -> List[FactCard]:
    """
    Sample fact cards extracted from clusters.
    """
    return [
        FactCard(
            story_id="cluster_fed_pause",
            entity="Federal Reserve",
            trend="Rate pause signaled",
            data_point="5.5% terminal rate",
            why_it_matters="Indicates peak in tightening cycle, supportive for equities",
            confidence=0.92,
            tickers=["SPY", "TLT"],
            sources=["Reuters"],
            urls=["https://reuters.com/markets/fed-pause-2026-01"]
        ),
        FactCard(
            story_id="cluster_tech_rally",
            entity="NVIDIA",
            trend="AI chip demand surge",
            data_point="Record $30B quarterly revenue",
            why_it_matters="Confirms AI infrastructure buildout momentum",
            confidence=0.95,
            tickers=["NVDA"],
            sources=["CNBC"],
            urls=["https://cnbc.com/nvda-earnings-2026-q4"]
        ),
        FactCard(
            story_id="cluster_ecb",
            entity="European Central Bank",
            trend="Maintains hawkish stance",
            data_point="4.5% deposit rate",
            why_it_matters="Euro strength pressures exporters, divergence with Fed",
            confidence=0.88,
            tickers=["EZU"],
            sources=["Financial Times"],
            urls=["https://ft.com/ecb-policy-2026-01"]
        )
    ]


@pytest.fixture
def mock_perplexity_response(sample_news_items) -> str:
    """
    Mock Perplexity API response as JSON string.
    """
    return json.dumps(sample_news_items)


@pytest.fixture
def mock_openai_extraction_response() -> Dict:
    """
    Mock OpenAI extraction response (fact cards).
    """
    return {
        "fact_cards": [
            {
                "story_id": "cluster_fed_pause",
                "entity": "Federal Reserve",
                "trend": "Rate pause signaled",
                "data_point": "5.5% terminal rate",
                "why_it_matters": "Indicates peak in tightening cycle",
                "confidence": 0.92,
                "tickers": ["SPY", "TLT"],
                "sources": ["Reuters"],
                "urls": ["https://reuters.com/markets/fed-pause-2026-01"]
            },
            {
                "story_id": "cluster_tech_rally",
                "entity": "NVIDIA",
                "trend": "AI chip demand surge",
                "data_point": "Record $30B revenue",
                "why_it_matters": "Confirms AI infrastructure buildout",
                "confidence": 0.95,
                "tickers": ["NVDA"],
                "sources": ["CNBC"],
                "urls": ["https://cnbc.com/nvda-earnings-2026-q4"]
            }
        ]
    }


@pytest.fixture
def mock_openai_composition_response() -> Dict:
    """
    Mock OpenAI composition response (daily brief).
    """
    return {
        "headline": "Markets Rally on Fed Pause Signal",
        "preheader": "Equities surge as Powell hints at policy shift",
        "intro": "U.S. markets extended gains as Federal Reserve Chair Jerome Powell signaled a pause in rate hikes.",
        "top5_md": "* **Fed Rate Pause**: Powell indicates terminal rate reached [Reuters]\n* **NVDA Earnings Beat**: AI chip demand drives record revenue [CNBC]\n* **Tech Rally Broadens**: Software and semiconductor sectors lead gains [Bloomberg]",
        "macro_md": "Central banks are entering a new phase as inflation cools. The Fed's dovish pivot is particularly significant given recent CPI data showing a 2.1% annual rate.",
        "watchlist_md": "* **NVDA**: +12% on earnings beat, AI demand remains strong\n* **SPY**: Tests resistance at 5,200 on macro optimism",
        "snapshot_md": "| Asset | Level | Context |\n|-------|-------|----------|\n| S&P 500 | 5,187 | +2.3% on Fed dovish pivot |\n| 10Y Treasury | 4.12% | -15bp as rate hike odds fade |"
    }


@pytest.fixture
def mock_sendgrid_client():
    """
    Mock SendGrid client for email testing.
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.body = "Accepted"
    mock_client.send.return_value = mock_response
    return mock_client


@pytest.fixture
def freezed_time():
    """
    Freeze time to a specific datetime for deterministic tests.
    """
    frozen = datetime(2026, 1, 31, 12, 0, 0)
    with patch('src.logging_utils.datetime') as mock_datetime:
        mock_datetime.now.return_value = frozen
        mock_datetime.strftime = datetime.strftime
        yield frozen

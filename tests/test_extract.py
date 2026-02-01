import pytest
from unittest.mock import MagicMock, patch
from src.extract import FactCardExtractor, FactCard
from src.clustering import StoryCluster
from src.retrieval import MarketNewsItem

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.daily.max_clusters = 14
    settings.openai_api_key.get_secret_value.return_value = "fake-key"
    settings.models.extract_model = "gpt-5-mini"
    settings.models.write_model = "gpt-5-mini"
    settings.models.fallback_model = "gpt-4o-mini"
    return settings

@pytest.fixture
def sample_cluster():
    primary_item = MarketNewsItem(
        title="Fed raises interest rates by 0.25%",
        source="Reuters",
        url="https://reuters.com/fed-rates",
        published_at="2024-01-01",
        snippet="The Federal Reserve raised interest rates by 25 basis points to 5.5%.",
        region="us"
    )
    
    supporting_item = MarketNewsItem(
        title="Central bank increases rates",
        source="Bloomberg",
        url="https://bloomberg.com/fed-decision",
        published_at="2024-01-01",
        snippet="Fed decision impacts markets.",
        region="us"
    )
    
    cluster = StoryCluster(
        cluster_id="fed_cluster_123",
        primary_item=primary_item,
        supporting_items=[supporting_item]
    )
    return cluster

def test_fact_card_validation():
    # Valid fact card
    valid_card = FactCard(
        story_id="test_123",
        entity="Federal Reserve",
        trend="Raised interest rates",
        data_point="0.25%",
        why_it_matters="Higher borrowing costs slow economic growth",
        confidence=0.9,
        tickers=["SPY"],
        sources=["Reuters"],
        urls=["https://reuters.com/test"]
    )
    assert valid_card.confidence == 0.9
    assert len(valid_card.sources) == 1

    # Invalid confidence
    with pytest.raises(Exception):
        FactCard(
            story_id="test_123",
            entity="Test",
            trend="Test trend",
            why_it_matters="Test matter",
            confidence=1.5,  # Invalid
            sources=["Test"],
            urls=["https://test.com"]
        )

@patch("src.extract.OpenAIClient")
def test_extract_fact_cards_success(mock_ai_class, mock_settings, sample_cluster):
    # Mock AI response
    mock_ai_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"fact_cards": [{"story_id": "fed_cluster_123", "entity": "Federal Reserve", "trend": "Raised rates", "data_point": "0.25%", "why_it_matters": "Higher borrowing costs", "confidence": 0.9, "tickers": ["SPY"], "sources": ["Reuters"], "urls": ["https://reuters.com/fed-rates"]}]}'))]
    mock_ai_instance.responses_create.return_value = mock_response
    mock_ai_class.return_value = mock_ai_instance
    
    extractor = FactCardExtractor(mock_settings)
    clusters = [sample_cluster]
    
    result = extractor.extract_fact_cards(clusters)
    
    assert len(result) == 1
    assert result[0].entity == "Federal Reserve"
    assert result[0].confidence == 0.9
    assert "Reuters" in result[0].sources

@patch("src.extract.OpenAIClient")
def test_extract_fact_cards_empty_clusters(mock_ai_class, mock_settings):
    extractor = FactCardExtractor(mock_settings)
    result = extractor.extract_fact_cards([])
    assert result == []

@patch("src.extract.OpenAIClient")
def test_extract_fact_cards_max_clusters_limit(mock_ai_class, mock_settings, sample_cluster):
    # Set max_clusters to 1
    mock_settings.daily.max_clusters = 1
    
    # Mock AI response
    mock_ai_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"fact_cards": []}'))]
    mock_ai_instance.responses_create.return_value = mock_response
    mock_ai_class.return_value = mock_ai_instance
    
    extractor = FactCardExtractor(mock_settings)
    
    # Create 3 clusters but expect only 1 to be processed
    clusters = [sample_cluster, sample_cluster, sample_cluster]
    extractor.extract_fact_cards(clusters)
    
    # Verify that only max_clusters were processed by checking the call
    mock_ai_instance.responses_create.assert_called_once()
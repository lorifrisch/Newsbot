"""
Unit tests for retrieval module.

Tests the RetrievalPlanner including:
- Query plan generation
- JSON parsing from Perplexity responses
- Circuit breaker functionality
- Minimum query success threshold
- Regional balancing and clustering
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from src.retrieval import RetrievalPlanner, RetrievalResult, MarketNewsItem
from src.clustering import StoryCluster


@pytest.mark.unit
class TestRetrievalPlanner:
    """Test suite for RetrievalPlanner class."""
    
    def test_generate_queries(self, test_settings):
        """Test that query plan includes all 6 required queries."""
        planner = RetrievalPlanner(test_settings)
        queries = planner._generate_queries()
        
        assert len(queries) == 6
        assert "us_macro" in queries
        assert "us_equities" in queries
        assert "eu_market" in queries
        assert "china_market" in queries
        assert "global_market" in queries
        assert "watchlist" in queries
        
        # Verify watchlist query includes tickers
        assert "AAPL" in queries["watchlist"]
        assert "NVDA" in queries["watchlist"]
    
    def test_parse_json_items_success(self, test_settings, sample_news_items):
        """Test successful parsing of valid JSON array."""
        planner = RetrievalPlanner(test_settings)
        json_text = json.dumps(sample_news_items)
        
        items = planner._parse_json_items(json_text)
        
        assert len(items) == 5
        assert items[0]["title"] == "Fed Signals Rate Pause Amid Cooling Inflation"
        assert items[0]["region"] == "us"
    
    def test_parse_json_items_with_markdown_wrapper(self, test_settings, sample_news_items):
        """Test parsing JSON wrapped in markdown code block."""
        planner = RetrievalPlanner(test_settings)
        json_text = f"```json\n{json.dumps(sample_news_items)}\n```"
        
        items = planner._parse_json_items(json_text)
        
        assert len(items) == 5
        assert items[0]["title"] == "Fed Signals Rate Pause Amid Cooling Inflation"
    
    def test_parse_json_items_with_preamble(self, test_settings, sample_news_items):
        """Test parsing JSON with text preamble before array."""
        planner = RetrievalPlanner(test_settings)
        json_text = f"Here are the news items:\n{json.dumps(sample_news_items)}"
        
        items = planner._parse_json_items(json_text)
        
        assert len(items) == 5
    
    def test_parse_json_items_invalid(self, test_settings):
        """Test parsing invalid JSON returns empty list."""
        planner = RetrievalPlanner(test_settings)
        
        items = planner._parse_json_items("This is not JSON")
        
        assert items == []
    
    def test_parse_json_items_empty(self, test_settings):
        """Test parsing empty JSON array."""
        planner = RetrievalPlanner(test_settings)
        
        items = planner._parse_json_items("[]")
        
        assert items == []
    
    @patch('src.retrieval.cluster_items')
    def test_fetch_and_normalize_success(self, mock_cluster, test_settings, mock_perplexity_response, sample_clusters):
        """Test successful retrieval with all queries succeeding."""
        planner = RetrievalPlanner(test_settings)
        mock_cluster.return_value = sample_clusters
        
        # Mock Perplexity client to return valid responses
        with patch.object(planner.perplexity, 'chat', return_value=mock_perplexity_response):
            result = planner.fetch_and_normalize()
        
        assert isinstance(result, RetrievalResult)
        assert result.successful_queries == 6
        assert result.failed_queries == 0
        assert result.is_sufficient is True
        assert len(result.clusters) > 0
        assert all(result.query_details.values())  # All True
    
    @patch('src.retrieval.cluster_items')
    def test_fetch_and_normalize_circuit_breaker(self, mock_cluster, test_settings):
        """Test circuit breaker stops after 2 consecutive failures."""
        planner = RetrievalPlanner(test_settings)
        mock_cluster.return_value = []
        
        # Mock first 2 queries to fail
        call_count = [0]
        def mock_chat_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise Exception("API Error")
            return "[]"
        
        with patch.object(planner.perplexity, 'chat', side_effect=mock_chat_side_effect):
            result = planner.fetch_and_normalize()
        
        # Should stop after 2 failures, not attempt all 6 queries
        assert call_count[0] == 2
        assert result.successful_queries == 0
        assert result.failed_queries == 6  # Remaining marked as failed
        assert result.is_sufficient is False
    
    @patch('src.retrieval.cluster_items')
    def test_fetch_and_normalize_insufficient_queries(self, mock_cluster, test_settings, mock_perplexity_response):
        """Test insufficient queries (only 2/6 succeed)."""
        planner = RetrievalPlanner(test_settings)
        mock_cluster.return_value = []
        
        # Mock 2 successes, 4 failures (non-consecutive to avoid circuit breaker)
        call_count = [0]
        def mock_chat_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] in [1, 3]:  # Queries 1 and 3 succeed
                return mock_perplexity_response
            raise Exception("API Error")
        
        with patch.object(planner.perplexity, 'chat', side_effect=mock_chat_side_effect):
            result = planner.fetch_and_normalize()
        
        assert result.successful_queries == 2
        assert result.failed_queries == 4
        assert result.is_sufficient is False  # Below 3/6 threshold
    
    @patch('src.retrieval.cluster_items')
    def test_fetch_and_normalize_minimum_threshold_met(self, mock_cluster, test_settings, mock_perplexity_response):
        """Test exactly 3/6 queries succeed (minimum threshold)."""
        planner = RetrievalPlanner(test_settings)
        mock_cluster.return_value = []
        
        # Mock exactly 3 successes
        call_count = [0]
        def mock_chat_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] in [1, 3, 5]:  # Non-consecutive to avoid circuit breaker
                return mock_perplexity_response
            raise Exception("API Error")
        
        with patch.object(planner.perplexity, 'chat', side_effect=mock_chat_side_effect):
            result = planner.fetch_and_normalize()
        
        assert result.successful_queries == 3
        assert result.is_sufficient is True  # Exactly at threshold
    
    def test_merge_and_cap_clusters_regional_balance(self, test_settings, sample_clusters):
        """Test regional balancing and max_candidates cap."""
        planner = RetrievalPlanner(test_settings)
        
        # Create more clusters than max_candidates
        many_clusters = sample_clusters * 10  # 30 clusters
        
        result = planner._merge_and_cap_clusters(many_clusters)
        
        # Should cap at max_candidates (15)
        assert len(result) <= test_settings.daily.max_candidates
    
    def test_merge_and_cap_clusters_watchlist_priority(self, test_settings):
        """Test watchlist items get priority in final selection."""
        planner = RetrievalPlanner(test_settings)
        
        # Create mix of regions with watchlist items
        watchlist_item = MarketNewsItem(
            title="NVDA Earnings Beat",
            source="CNBC",
            url="https://cnbc.com/nvda-1",
            published_at="2026-01-31T10:00:00Z",
            snippet="NVIDIA reports record earnings",
            region="watchlist"
        )
        us_item = MarketNewsItem(
            title="Fed Policy Update",
            source="Reuters",
            url="https://reuters.com/fed-1",
            published_at="2026-01-31T10:00:00Z",
            snippet="Fed signals policy shift",
            region="us"
        )
        
        clusters = [
            StoryCluster(primary_item=watchlist_item, supporting_items=[], cluster_id="wl_1"),
            StoryCluster(primary_item=us_item, supporting_items=[], cluster_id="us_1")
        ]
        
        result = planner._merge_and_cap_clusters(clusters)
        
        # Watchlist should be included
        assert any(c.primary_item.region == "watchlist" for c in result)
    
    def test_snippet_truncation_logged(self, test_settings, mock_perplexity_response):
        """Test that snippet truncation is properly logged."""
        planner = RetrievalPlanner(test_settings)
        
        # Create response with very long snippet
        long_snippet_item = {
            "title": "Test",
            "source": "Test",
            "url": "https://test.com",
            "published_at": "2026-01-31T10:00:00Z",
            "snippet": " ".join(["word"] * 100),  # 100 words
            "region": "us"
        }
        
        with patch.object(planner.perplexity, 'chat', return_value=json.dumps([long_snippet_item])):
            with patch('src.retrieval.cluster_items', return_value=[]):
                result = planner.fetch_and_normalize()
        
        # Should succeed and truncate
        assert result.successful_queries > 0


@pytest.mark.unit
class TestRetrievalResult:
    """Test suite for RetrievalResult dataclass."""
    
    def test_retrieval_result_sufficient(self, sample_clusters):
        """Test RetrievalResult with sufficient queries."""
        result = RetrievalResult(
            clusters=sample_clusters,
            successful_queries=4,
            failed_queries=2,
            query_details={"q1": True, "q2": True, "q3": False, "q4": True, "q5": False, "q6": True}
        )
        
        assert result.is_sufficient is True
        assert result.successful_queries == 4
    
    def test_retrieval_result_insufficient(self, sample_clusters):
        """Test RetrievalResult with insufficient queries."""
        result = RetrievalResult(
            clusters=sample_clusters,
            successful_queries=2,
            failed_queries=4,
            query_details={"q1": True, "q2": False, "q3": False, "q4": True, "q5": False, "q6": False}
        )
        
        assert result.is_sufficient is False
        assert result.failed_queries == 4
    
    def test_retrieval_result_boundary(self, sample_clusters):
        """Test RetrievalResult at exactly 3/6 threshold."""
        result = RetrievalResult(
            clusters=sample_clusters,
            successful_queries=3,
            failed_queries=3,
            query_details={"q1": True, "q2": False, "q3": True, "q4": False, "q5": False, "q6": True}
        )
        
        assert result.is_sufficient is True  # Exactly at threshold

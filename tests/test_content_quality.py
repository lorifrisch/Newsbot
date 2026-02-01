"""
Content Quality Tests
=====================

Tests to validate that the daily brief meets quality thresholds:
- Exactly 5 top stories
- EU and China coverage (or explicit note)
- All 10 watchlist tickers appear
- Minimum clickable links
- Real market data present
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import List, Dict, Set

from src.metrics import PipelineMetrics, RankingMetrics, WatchlistMetrics, OutputMetrics
from src.templates import EmailFormatter
from src.compose import _group_watchlist_by_ticker, _format_watchlist_context_by_ticker


# ============================================================================
# Fixtures
# ============================================================================

@dataclass
class MockFactCard:
    entity: str
    trend: str
    why_it_matters: str
    data_point: str
    confidence: float
    sources: List[str]
    tickers: List[str]
    url: str = ""


@pytest.fixture
def sample_watchlist():
    return {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"}


@pytest.fixture
def sample_cards(sample_watchlist):
    """Create sample fact cards with watchlist tickers."""
    cards = []
    tickers = list(sample_watchlist)
    for i, ticker in enumerate(tickers[:7]):  # Only 7 covered
        cards.append(MockFactCard(
            entity=f"{ticker} Corp",
            trend=f"{ticker} stock moved significantly",
            why_it_matters=f"Impact analysis for {ticker}",
            data_point=f"+{i+1}%",
            confidence=0.9 - i * 0.05,
            sources=["Reuters", "Bloomberg"],
            tickers=[ticker],
            url=f"https://example.com/{ticker.lower()}"
        ))
    return cards


@pytest.fixture
def email_formatter():
    return EmailFormatter()


# ============================================================================
# Test: Top 5 Stories Count
# ============================================================================

class TestTop5Count:
    """Tests for ensuring exactly 5 top stories."""
    
    def test_metrics_validates_top5_count(self):
        """Metrics should flag if Top 5 has wrong count."""
        metrics = PipelineMetrics()
        metrics.ranking.top5_count = 3  # Too few
        
        issues = metrics.validate_quality()
        assert any("Top 5" in issue for issue in issues)
    
    def test_metrics_passes_with_5_stories(self):
        """Metrics should pass with exactly 5 top stories."""
        metrics = PipelineMetrics()
        metrics.ranking.top5_count = 5
        metrics.ranking.has_eu_in_top5 = True
        metrics.ranking.has_china_in_top5 = True
        metrics.watchlist.tickers_expected = 10
        metrics.watchlist.tickers_in_output = 10
        metrics.output.total_clickable_links = 15
        
        issues = metrics.validate_quality()
        assert not any("Top 5" in issue for issue in issues)


# ============================================================================
# Test: Regional Coverage
# ============================================================================

class TestRegionalCoverage:
    """Tests for EU and China coverage in Top 5."""
    
    def test_metrics_flags_missing_eu(self):
        """Should flag if no EU story in Top 5."""
        metrics = PipelineMetrics()
        metrics.ranking.top5_count = 5
        metrics.ranking.has_eu_in_top5 = False
        metrics.ranking.has_china_in_top5 = True
        
        issues = metrics.validate_quality()
        assert any("EU" in issue for issue in issues)
    
    def test_metrics_flags_missing_china(self):
        """Should flag if no China story in Top 5."""
        metrics = PipelineMetrics()
        metrics.ranking.top5_count = 5
        metrics.ranking.has_eu_in_top5 = True
        metrics.ranking.has_china_in_top5 = False
        
        issues = metrics.validate_quality()
        assert any("China" in issue for issue in issues)
    
    def test_metrics_passes_with_regional_coverage(self):
        """Should pass with both EU and China coverage."""
        metrics = PipelineMetrics()
        metrics.ranking.top5_count = 5
        metrics.ranking.has_eu_in_top5 = True
        metrics.ranking.has_china_in_top5 = True
        metrics.watchlist.tickers_expected = 10
        metrics.watchlist.tickers_in_output = 10
        metrics.output.total_clickable_links = 15
        
        issues = metrics.validate_quality()
        # Should not have EU or China issues
        assert not any("EU" in issue for issue in issues)
        assert not any("China" in issue for issue in issues)


# ============================================================================
# Test: Watchlist Coverage
# ============================================================================

class TestWatchlistCoverage:
    """Tests for all 10 watchlist tickers appearing."""
    
    def test_group_watchlist_by_ticker(self, sample_cards, sample_watchlist):
        """Should group cards by ticker."""
        grouped = _group_watchlist_by_ticker(sample_cards, sample_watchlist, max_per_ticker=2)
        
        # Should have entries for covered tickers
        assert len(grouped) == 7  # 7 cards for 7 tickers
        
        # Each ticker should have at most 2 cards
        for ticker, cards in grouped.items():
            assert len(cards) <= 2
    
    def test_format_shows_all_tickers(self, sample_cards, sample_watchlist):
        """Should show all 10 watchlist tickers, even uncovered ones."""
        grouped = _group_watchlist_by_ticker(sample_cards, sample_watchlist)
        formatted = _format_watchlist_context_by_ticker(grouped, sample_watchlist)
        
        # All 10 tickers should appear
        for ticker in sample_watchlist:
            assert ticker in formatted
        
        # Uncovered tickers should have "No major updates"
        uncovered = sample_watchlist - set(t for c in sample_cards for t in c.tickers)
        for ticker in uncovered:
            assert "No major updates" in formatted
    
    def test_metrics_flags_low_watchlist_coverage(self):
        """Should flag if fewer than 10 watchlist tickers in output."""
        metrics = PipelineMetrics()
        metrics.watchlist.tickers_expected = 10
        metrics.watchlist.tickers_in_output = 5  # Only half
        
        issues = metrics.validate_quality()
        assert any("watchlist" in issue.lower() for issue in issues)
    
    def test_metrics_passes_full_watchlist_coverage(self):
        """Should pass with all 10 watchlist tickers."""
        metrics = PipelineMetrics()
        metrics.ranking.top5_count = 5
        metrics.ranking.has_eu_in_top5 = True
        metrics.ranking.has_china_in_top5 = True
        metrics.watchlist.tickers_expected = 10
        metrics.watchlist.tickers_in_output = 10
        metrics.output.total_clickable_links = 15
        
        issues = metrics.validate_quality()
        assert not any("watchlist" in issue.lower() for issue in issues)


# ============================================================================
# Test: Clickable Citations
# ============================================================================

class TestClickableCitations:
    """Tests for clickable source links."""
    
    def test_md_to_html_converts_links(self, email_formatter):
        """Should convert Markdown links to HTML anchors."""
        md = "Check out [Reuters](https://reuters.com) for more."
        html = email_formatter.md_to_html(md)
        
        assert '<a href="https://reuters.com"' in html
        assert '>Reuters</a>' in html
    
    def test_md_to_html_styles_links(self, email_formatter):
        """Links should have inline styles for email clients."""
        md = "[Source](https://example.com)"
        html = email_formatter.md_to_html(md)
        
        assert 'style="' in html
        assert 'color:' in html
    
    def test_count_clickable_links(self, email_formatter):
        """Should accurately count clickable links."""
        html = '''
        <p>See <a href="https://a.com">A</a> and <a href="https://b.com">B</a>.</p>
        <p>Also <a href="https://c.com">C</a>.</p>
        '''
        count = email_formatter.count_clickable_links(html)
        assert count == 3
    
    def test_metrics_flags_low_link_count(self):
        """Should flag if fewer than 10 clickable links."""
        metrics = PipelineMetrics()
        metrics.output.total_clickable_links = 5  # Too few
        
        issues = metrics.validate_quality()
        assert any("link" in issue.lower() for issue in issues)
    
    def test_metrics_passes_sufficient_links(self):
        """Should pass with 10+ clickable links."""
        metrics = PipelineMetrics()
        metrics.ranking.top5_count = 5
        metrics.ranking.has_eu_in_top5 = True
        metrics.ranking.has_china_in_top5 = True
        metrics.watchlist.tickers_expected = 10
        metrics.watchlist.tickers_in_output = 10
        metrics.output.total_clickable_links = 15
        
        issues = metrics.validate_quality()
        assert not any("link" in issue.lower() for issue in issues)


# ============================================================================
# Test: Market Data
# ============================================================================

class TestMarketData:
    """Tests for real market data integration."""
    
    def test_market_data_fetcher_import(self):
        """Market data fetcher should be importable."""
        from src.market_data import MarketDataFetcher, AssetQuote
        assert MarketDataFetcher is not None
        assert AssetQuote is not None
    
    def test_asset_quote_dataclass(self):
        """AssetQuote should hold market data properly."""
        from src.market_data import AssetQuote
        
        quote = AssetQuote(
            symbol="^GSPC",
            name="S&P 500",
            price=5000.0,
            change_pct=1.5,
            as_of="2025-01-15 16:00"
        )
        
        assert quote.symbol == "^GSPC"
        assert quote.price == 5000.0
        assert quote.change_pct == 1.5


# ============================================================================
# Test: Full Pipeline Metrics
# ============================================================================

class TestPipelineMetrics:
    """Tests for the full metrics tracking system."""
    
    def test_metrics_to_dict(self):
        """Should serialize to dictionary."""
        metrics = PipelineMetrics()
        metrics.retrieval.total_items_fetched = 50
        metrics.ranking.top5_count = 5
        
        d = metrics.to_dict()
        
        assert "retrieval" in d
        assert "ranking" in d
        assert d["retrieval"]["total_items_fetched"] == 50
        assert d["ranking"]["top5_count"] == 5
    
    def test_metrics_print_quality_report(self, capsys):
        """Should print formatted quality report."""
        metrics = PipelineMetrics()
        metrics.retrieval.total_items_fetched = 50
        metrics.retrieval.us_items = 30
        metrics.retrieval.eu_items = 12
        metrics.retrieval.china_items = 8
        metrics.ranking.top5_count = 5
        metrics.watchlist.tickers_expected = 10
        metrics.watchlist.tickers_in_output = 10
        metrics.output.total_clickable_links = 20
        
        metrics.print_quality_report()
        
        captured = capsys.readouterr()
        assert "50" in captured.out  # total items
        assert "5" in captured.out   # top 5
    
    def test_validate_quality_returns_list(self):
        """validate_quality should return a list of issues."""
        metrics = PipelineMetrics()
        issues = metrics.validate_quality()
        
        assert isinstance(issues, list)


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

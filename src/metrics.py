"""
Pipeline Metrics - Instrumentation for content quality tracking.

Tracks counts at each stage of the pipeline:
- Retrieved items by region and type
- Deduplication and clustering counts
- Fact card extraction counts
- Selection/ranking counts per bucket
- Coverage metrics (tickers, regions)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RetrievalMetrics:
    """Metrics from the retrieval phase."""
    total_items: int = 0
    by_region: Dict[str, int] = field(default_factory=dict)
    by_query: Dict[str, int] = field(default_factory=dict)
    watchlist_items: int = 0
    non_watchlist_items: int = 0
    items_with_valid_urls: int = 0
    items_dropped_no_url: int = 0
    domain_filtered_count: int = 0
    successful_queries: int = 0
    failed_queries: int = 0


@dataclass
class ClusteringMetrics:
    """Metrics from clustering/deduplication."""
    items_before_dedup: int = 0
    clusters_after_dedup: int = 0
    dedup_ratio: float = 0.0  # items_before / clusters_after


@dataclass
class ExtractionMetrics:
    """Metrics from fact card extraction."""
    clusters_input: int = 0
    fact_cards_extracted: int = 0
    extraction_rate: float = 0.0  # cards / clusters


@dataclass
class RankingMetrics:
    """Metrics from ranking and selection."""
    fact_cards_input: int = 0
    top5_selected: int = 0
    macro_items: int = 0
    watchlist_items: int = 0
    company_markets_items: int = 0
    # Regional coverage in Top 5
    top5_us_count: int = 0
    top5_eu_count: int = 0
    top5_china_count: int = 0
    top5_other_count: int = 0
    # China coverage status
    china_news_available: bool = False
    china_note_added: bool = False


@dataclass
class WatchlistMetrics:
    """Metrics for watchlist coverage."""
    total_tickers_configured: int = 0
    tickers_with_news: int = 0
    tickers_without_news: int = 0
    covered_tickers: List[str] = field(default_factory=list)
    uncovered_tickers: List[str] = field(default_factory=list)
    items_per_ticker: Dict[str, int] = field(default_factory=dict)


@dataclass
class OutputMetrics:
    """Metrics for output quality."""
    total_clickable_links: int = 0
    snapshot_has_data: bool = False
    snapshot_status: str = "unknown"  # "real_data", "unavailable", "ai_generated"
    word_count_estimate: int = 0
    read_time_minutes: float = 0.0


@dataclass 
class PipelineMetrics:
    """Complete metrics for a pipeline run."""
    run_id: str = ""
    timestamp: str = ""
    mode: str = "production"  # or "dry_run"
    
    retrieval: RetrievalMetrics = field(default_factory=RetrievalMetrics)
    clustering: ClusteringMetrics = field(default_factory=ClusteringMetrics)
    extraction: ExtractionMetrics = field(default_factory=ExtractionMetrics)
    ranking: RankingMetrics = field(default_factory=RankingMetrics)
    watchlist: WatchlistMetrics = field(default_factory=WatchlistMetrics)
    output: OutputMetrics = field(default_factory=OutputMetrics)
    
    # Quality flags
    quality_passed: bool = True
    quality_issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def save(self, run_dir: Path) -> None:
        """Save metrics to JSON file in run directory."""
        metrics_path = run_dir / "metrics.json"
        with open(metrics_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Metrics saved to {metrics_path}")
    
    def validate_quality(self, watchlist_tickers: List[str]) -> None:
        """Run quality checks and populate quality_issues."""
        self.quality_issues = []
        
        # Check Top 5 count
        if self.ranking.top5_selected != 5:
            self.quality_issues.append(
                f"Top 5 has {self.ranking.top5_selected} items (expected exactly 5)"
            )
        
        # Check EU coverage
        if self.ranking.top5_eu_count == 0 and self.retrieval.by_region.get('eu', 0) > 0:
            self.quality_issues.append("No EU story in Top 5 despite EU news being available")
        
        # Check China coverage
        if not self.ranking.china_news_available and not self.ranking.china_note_added:
            self.quality_issues.append("No China news and no 'no China news' note added")
        
        # Check watchlist coverage
        total_tickers = len(watchlist_tickers)
        if self.watchlist.tickers_with_news < min(5, total_tickers):
            self.quality_issues.append(
                f"Only {self.watchlist.tickers_with_news}/{total_tickers} watchlist tickers covered"
            )
        
        # Check clickable links
        if self.output.total_clickable_links < 10:
            self.quality_issues.append(
                f"Only {self.output.total_clickable_links} clickable links (expected at least 10)"
            )
        
        # Check snapshot
        if self.output.snapshot_status == "ai_generated":
            self.quality_issues.append("Snapshot uses AI-generated data instead of real market data")
        
        self.quality_passed = len(self.quality_issues) == 0
    
    def print_quality_report(self) -> None:
        """Print a formatted quality report to logger."""
        logger.info("=" * 60)
        logger.info("QUALITY REPORT")
        logger.info("=" * 60)
        
        # Retrieval summary
        logger.info(f"📥 RETRIEVAL:")
        logger.info(f"   Total items: {self.retrieval.total_items}")
        logger.info(f"   By region: {self.retrieval.by_region}")
        logger.info(f"   Watchlist items: {self.retrieval.watchlist_items}")
        logger.info(f"   Items dropped (no URL): {self.retrieval.items_dropped_no_url}")
        
        # Clustering summary
        logger.info(f"🔗 CLUSTERING:")
        logger.info(f"   Before dedup: {self.clustering.items_before_dedup}")
        logger.info(f"   After clustering: {self.clustering.clusters_after_dedup}")
        
        # Extraction summary
        logger.info(f"📝 EXTRACTION:")
        logger.info(f"   Fact cards: {self.extraction.fact_cards_extracted}")
        logger.info(f"   Rate: {self.extraction.extraction_rate:.1%}")
        
        # Ranking summary
        logger.info(f"📊 RANKING:")
        logger.info(f"   Top 5: {self.ranking.top5_selected} (US:{self.ranking.top5_us_count}, EU:{self.ranking.top5_eu_count}, China:{self.ranking.top5_china_count})")
        logger.info(f"   Macro: {self.ranking.macro_items}")
        logger.info(f"   Watchlist bucket: {self.ranking.watchlist_items}")
        
        # Watchlist coverage
        logger.info(f"👀 WATCHLIST COVERAGE:")
        logger.info(f"   Configured: {self.watchlist.total_tickers_configured} tickers")
        logger.info(f"   With news: {self.watchlist.tickers_with_news} ({', '.join(self.watchlist.covered_tickers[:5])}{'...' if len(self.watchlist.covered_tickers) > 5 else ''})")
        logger.info(f"   Without news: {self.watchlist.tickers_without_news} ({', '.join(self.watchlist.uncovered_tickers[:5])}{'...' if len(self.watchlist.uncovered_tickers) > 5 else ''})")
        
        # Output quality
        logger.info(f"📤 OUTPUT:")
        logger.info(f"   Clickable links: {self.output.total_clickable_links}")
        logger.info(f"   Snapshot status: {self.output.snapshot_status}")
        logger.info(f"   Est. read time: {self.output.read_time_minutes:.1f} min")
        
        # Quality assessment
        logger.info("=" * 60)
        if self.quality_passed:
            logger.info("✅ QUALITY CHECK: PASSED")
        else:
            logger.warning("❌ QUALITY CHECK: FAILED")
            for issue in self.quality_issues:
                logger.warning(f"   • {issue}")
        logger.info("=" * 60)


def count_clickable_links(html_content: str) -> int:
    """Count the number of <a href= links in HTML content."""
    import re
    pattern = r'<a\s+[^>]*href\s*=\s*["\'][^"\']+["\']'
    matches = re.findall(pattern, html_content, re.IGNORECASE)
    return len(matches)


def estimate_read_time(html_content: str) -> float:
    """Estimate reading time in minutes based on word count."""
    import re
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # Count words
    words = len(text.split())
    # Average reading speed: 200 words per minute
    return words / 200.0

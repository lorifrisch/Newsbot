#!/usr/bin/env python3
"""
Daily Markets Brief Workflow
=============================

Orchestrates the complete end-to-end pipeline:
1. Initialize database
2. Retrieve candidates (Perplexity API with rate limits)
3. Deduplicate & cluster articles
4. Extract fact cards (OpenAI)
5. Rank and select top stories
6. Compose analytical brief (OpenAI)
7. Send email (SendGrid)
8. Store artifacts and report metadata

Usage:
    python run_daily.py              # Full execution with email send
    python run_daily.py --dry-run    # Generate artifacts only, no send
"""

import argparse
import sys
import logging
from datetime import datetime
from pathlib import Path

from src.config import Settings
from src.compose import DailyBriefComposer
from src.templates import EmailFormatter
from src.retrieval import RetrievalPlanner
from src.storage import NewsStorage
from src.mailer import NewsMailer
from src.extract import FactCardExtractor
from src.rank import FactCardRanker
from src.logging_utils import setup_logging, save_artifact, cleanup_old_runs
from src.market_data import MarketDataFetcher
from src.metrics import PipelineMetrics


def run_daily_workflow(dry_run: bool = False):
    """
    Execute the complete daily brief workflow.
    
    Args:
        dry_run: If True, generate artifacts and HTML but do not send email.
    """
    
    # =============================
    # PHASE 0: INITIALIZATION
    # =============================
    settings = Settings.load()
    run_id, run_dir = setup_logging(settings.app.log_level)
    logger = logging.getLogger(__name__)
    
    mode_label = "DRY RUN" if dry_run else "PRODUCTION"
    logger.info(f"=" * 60)
    logger.info(f"DAILY BRIEF WORKFLOW - {mode_label}")
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Artifacts: {run_dir}")
    logger.info(f"=" * 60)
    
    # Cleanup old run artifacts (keep last 10 days)
    cleanup_old_runs(days_to_keep=10)
    
    try:
        # Initialize components
        logger.info("Initializing components...")
        planner = RetrievalPlanner(settings)
        composer = DailyBriefComposer(settings)
        formatter = EmailFormatter()
        extractor = FactCardExtractor(settings)
        ranker = FactCardRanker(settings)
        db = NewsStorage(settings.database_path)
        mailer = NewsMailer(settings)
        market_data = MarketDataFetcher(settings)
        
        # Initialize metrics tracking
        metrics = PipelineMetrics()
        watchlist_set = set(t.upper() for t in settings.watchlist_tickers)
        
        # =============================
        # PHASE 1: RETRIEVAL
        # =============================
        logger.info("PHASE 1: Fetching market news from Perplexity...")
        retrieval_result = planner.fetch_and_normalize()
        
        # Track retrieval metrics
        metrics.retrieval.total_items = sum(retrieval_result.items_by_query.values()) if retrieval_result.items_by_query else 0
        metrics.retrieval.by_region = {
            "us": retrieval_result.items_by_region.get("us", 0),
            "eu": retrieval_result.items_by_region.get("eu", 0),
            "china": retrieval_result.items_by_region.get("china", 0)
        }
        metrics.retrieval.items_dropped_no_url = retrieval_result.items_dropped_no_url
        metrics.retrieval.watchlist_items = len(retrieval_result.watchlist_tickers_covered) if retrieval_result.watchlist_tickers_covered else 0
        metrics.retrieval.successful_queries = retrieval_result.successful_queries
        metrics.retrieval.failed_queries = retrieval_result.failed_queries
        
        # Log retrieval metadata
        logger.info(
            f"Retrieval complete: {retrieval_result.successful_queries}/{retrieval_result.successful_queries + retrieval_result.failed_queries} queries succeeded"
        )
        logger.info(f"Regional coverage: US={metrics.retrieval.by_region['us']}, EU={metrics.retrieval.by_region['eu']}, China={metrics.retrieval.by_region['china']}")
        
        if retrieval_result.failed_queries > 0:
            failed_keys = [k for k, v in retrieval_result.query_details.items() if not v]
            logger.warning(f"Failed queries: {', '.join(failed_keys)}")
        
        # Check minimum threshold
        if not retrieval_result.is_sufficient:
            logger.error(
                f"❌ Insufficient retrieval quality: only {retrieval_result.successful_queries}/6 queries succeeded. "
                f"Minimum threshold is 3/6. Aborting workflow."
            )
            return False
        
        clusters = retrieval_result.clusters
        save_artifact(run_dir, "01_retrieval_clusters", [c.model_dump() for c in clusters])
        
        if not clusters:
            logger.warning("⚠️  No news clusters fetched. Aborting workflow.")
            return False
        
        # Track clustering metrics
        metrics.clustering.items_before_dedup = metrics.retrieval.total_items
        metrics.clustering.clusters_after_dedup = len(clusters)
        logger.info(f"✓ Retrieved {len(clusters)} news clusters")
        
        # =============================
        # PHASE 2: EXTRACTION
        # =============================
        logger.info("PHASE 2: Extracting structured fact cards...")
        fact_cards = extractor.extract_fact_cards(clusters)
        save_artifact(run_dir, "02_extracted_fact_cards", [card.model_dump() for card in fact_cards])
        
        if not fact_cards:
            logger.warning("⚠️  No fact cards extracted. Aborting workflow.")
            return False
        
        # Track extraction metrics
        metrics.extraction.clusters_input = len(clusters)
        metrics.extraction.fact_cards_extracted = len(fact_cards)
        metrics.extraction.extraction_rate = len(fact_cards) / len(clusters) if clusters else 0
        logger.info(f"✓ Extracted {len(fact_cards)} fact cards")
        
        # =============================
        # PHASE 3: RANKING & SELECTION
        # =============================
        logger.info("PHASE 3: Ranking and bucketing stories...")
        buckets = ranker.rank_cards(fact_cards, clusters)
        
        # Track ranking metrics
        metrics.ranking.fact_cards_input = len(fact_cards)
        metrics.ranking.top5_selected = len(buckets.get("top_stories", []))
        metrics.ranking.macro_items = len(buckets.get("macro_policy", []))
        metrics.ranking.company_markets_items = len(buckets.get("company_markets", []))
        metrics.ranking.watchlist_items = len(buckets.get("watchlist", []))
        
        # Track regional coverage in Top 5 (already counts in buckets['top5_regions'])
        top5_regions_metrics = buckets.get("top5_regions", {})
        metrics.ranking.top5_us_count = top5_regions_metrics.get("us", 0)
        metrics.ranking.top5_eu_count = top5_regions_metrics.get("eu", 0)
        metrics.ranking.top5_china_count = top5_regions_metrics.get("china", 0)
        metrics.ranking.top5_other_count = top5_regions_metrics.get("other", 0)
            
        metrics.ranking.china_news_available = buckets.get("china_news_available", False)
        metrics.ranking.china_note_added = buckets.get("china_note_needed", False)
        
        # Extract sentiment before saving (sentiment_summary is not serializable as-is)
        sentiment_summary = buckets.get("sentiment_summary")
        buckets_for_save = {k: ([c.model_dump() for c in v] if isinstance(v, list) else v) 
                           for k, v in buckets.items()}
        save_artifact(run_dir, "03_ranked_buckets", buckets_for_save)
        
        bucket_summary = ", ".join([f"{k}: {len(v)}" for k, v in buckets.items() if isinstance(v, list)])
        logger.info(f"✓ Ranked and bucketed stories ({bucket_summary})")
        
        # =============================
        # PHASE 3.5: MARKET DATA
        # =============================
        logger.info("PHASE 3.5: Fetching real-time market data...")
        market_snapshot_html = ""
        if settings.market_data.use_real_data:
            try:
                # format_snapshot_html both fetches and formats
                market_snapshot_html = market_data.format_snapshot_html()
                logger.info("✓ Generated market data snapshot")
            except Exception as e:
                logger.warning(f"⚠️  Market data fetch failed: {e}")
        else:
            logger.info("Market data disabled in config, skipping")
        
        # =============================
        # PHASE 4: COMPOSITION
        # =============================
        logger.info("PHASE 4: Composing analytical brief with OpenAI...")
        report_raw = composer.compose_daily_brief(buckets, market_snapshot_html=market_snapshot_html)
        
        # Transform Markdown sections to styled HTML
        report_data = {
            "headline_title": report_raw["headline"],
            "intro_paragraph": report_raw["intro"],
            "top5_html": formatter.md_to_html(report_raw["top5_md"]),
            "macro_html": formatter.md_to_html(report_raw["macro_md"]),
            "watchlist_html": formatter.md_to_html(report_raw["watchlist_md"]),
            "snapshot_html": report_raw.get("snapshot_html") or formatter.md_to_html(report_raw.get("snapshot_md", "")),
            "what_to_watch_html": formatter.md_to_html(report_raw.get("what_to_watch_md", "")),
            "preheader": report_raw["preheader"]
        }
        
        # Track watchlist metrics
        watchlist_expected = report_raw.get("watchlist_tickers_expected", list(watchlist_set))
        watchlist_html = report_data["watchlist_html"]
        
        metrics.watchlist.total_tickers_configured = len(watchlist_expected)
        covered_in_output = set()
        for ticker in watchlist_expected:
            ticker_upper = ticker.upper()
            # Look for ticker in bold or just the ticker followed by a colon
            if f"**{ticker_upper}**" in watchlist_html.upper() or f"{ticker_upper}:" in watchlist_html.upper():
                # Check if it has news or just "No major updates"
                idx = watchlist_html.upper().find(ticker_upper)
                snippet = watchlist_html.upper()[idx:idx+120]
                if "NO MAJOR UPDATES" not in snippet:
                    covered_in_output.add(ticker_upper)
        
        metrics.watchlist.tickers_with_news = len(covered_in_output)
        metrics.watchlist.tickers_without_news = len(watchlist_expected) - len(covered_in_output)
        metrics.watchlist.covered_tickers = sorted(list(covered_in_output))
        metrics.watchlist.uncovered_tickers = sorted(list(set(watchlist_expected) - covered_in_output))
        
        # Add sentiment gauge if available
        sentiment_gauge_html = ""
        if sentiment_summary:
            try:
                from src.charts import sentiment_gauge
                gauge_img = sentiment_gauge(sentiment_summary.get("overall_score", 0))
                if gauge_img:
                    signal = sentiment_summary.get("signal", "⚪ Neutral")
                    sentiment_gauge_html = f'''
                    <div style="margin: 16px 0; padding: 16px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">
                            Market Sentiment
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <img src="{gauge_img}" alt="Sentiment Gauge" style="height: 20px; border-radius: 4px;"/>
                            <span style="font-size: 14px; font-weight: 600; color: #374151;">{signal}</span>
                        </div>
                        <div style="font-size: 12px; color: #6b7280; margin-top: 8px;">
                            {sentiment_summary.get("summary", "")}
                        </div>
                    </div>
                    '''
                    logger.info("✓ Generated sentiment gauge chart")
            except Exception as e:
                logger.debug(f"Sentiment gauge not generated: {e}")
        
        report_data["sentiment_html"] = sentiment_gauge_html
        save_artifact(run_dir, "04_brief_composition", report_data)
        logger.info(f"✓ Composed brief: '{report_data['headline_title']}'")
        
        # Debug logging: Preview HTML content blocks
        logger.debug(f"top5_html preview (first 200 chars): {report_data['top5_html'][:200]}")
        logger.debug(f"macro_html preview (first 200 chars): {report_data['macro_html'][:200]}")
        logger.debug(f"snapshot_html preview (first 200 chars): {report_data['snapshot_html'][:200]}")
        logger.debug(f"watchlist_html preview (first 200 chars): {report_data['watchlist_html'][:200]}")
        if sentiment_gauge_html:
            logger.debug(f"sentiment_html preview (first 200 chars): {sentiment_gauge_html[:200]}")
        
        # =============================
        # PHASE 5: RENDERING
        # =============================
        logger.info("PHASE 5: Rendering email template...")
        now = datetime.now()
        
        email_context = {
            "headline_title": report_data["headline_title"],
            "intro_paragraph": report_data["intro_paragraph"],
            "top5_html": report_data["top5_html"],
            "macro_html": report_data["macro_html"],
            "snapshot_html": report_data["snapshot_html"],
            "watchlist_html": report_data["watchlist_html"],
            "what_to_watch_html": report_data.get("what_to_watch_html", ""),
            "sentiment_html": report_data.get("sentiment_html", ""),
            "preheader": report_data["preheader"],
            "date_label": now.strftime("%A, %b %d, %Y"),
            "generated_time": now.strftime("%H:%M %Z"),
            "archive_url": "#",
            "preferences_url": "#"
        }
        
        html_content = mailer.render_content("email_template.html", email_context)
        
        # Debug logging: Check for escaped HTML sequences
        if "&lt;" in html_content:
            escaped_count = html_content.count("&lt;")
            logger.warning(f"⚠️  Detected {escaped_count} escaped HTML sequences (&lt;) in final output")
            # Find first occurrence for debugging
            idx = html_content.find("&lt;")
            if idx >= 0:
                snippet = html_content[max(0, idx-50):min(len(html_content), idx+150)]
                logger.warning(f"Example: ...{snippet}...")
        else:
            logger.info("✓ No escaped HTML sequences detected in final output")
        
        save_artifact(run_dir, "05_final_email", html_content, extension="html")
        logger.info(f"✓ Rendered email HTML ({len(html_content)} bytes)")
        
        # Track output metrics
        metrics.output.total_clickable_links = formatter.count_clickable_links(html_content)
        metrics.output.snapshot_has_data = bool(market_snapshot_html)
        metrics.output.snapshot_status = "real_data" if market_snapshot_html else "unavailable"
        metrics.output.word_count_estimate = len(html_content.split()) # Rough
        
        # Log quality metrics
        metrics.print_quality_report()
        
        # Validate quality thresholds
        metrics.validate_quality(watchlist_expected)
        if not metrics.quality_passed:
            logger.warning("⚠️  Quality issues detected:")
            for issue in metrics.quality_issues:
                logger.warning(f"   - {issue}")
        else:
            logger.info("✓ All quality thresholds passed")
        
        # Save metrics to artifact
        metrics.save(run_dir)
        
        # =============================
        # PHASE 6: STORAGE
        # =============================
        logger.info("PHASE 6: Persisting data to database...")
        
        # Store raw news items
        all_items = []
        for c in clusters:
            all_items.append(c.primary_item.model_dump())
            for s in c.supporting_items:
                all_items.append(s.model_dump())
        db.insert_items(all_items)
        logger.info(f"✓ Stored {len(all_items)} raw news items")
        
        # Store fact cards for weekly recap
        db.insert_fact_cards([card.model_dump() for card in fact_cards])
        logger.info(f"✓ Stored {len(fact_cards)} fact cards")
        
        # Store report metadata
        report_id = db.insert_report(
            kind="daily",
            subject=report_data["headline_title"],
            body_html=html_content,
            meta=report_data
        )
        logger.info(f"✓ Stored report metadata (ID: {report_id})")
        
        # =============================
        # PHASE 7: DELIVERY
        # =============================
        if dry_run:
            logger.info("=" * 60)
            logger.info("DRY RUN MODE: Skipping email send")
            logger.info(f"HTML saved to: {run_dir}/05_final_email.html")
            logger.info("=" * 60)
        else:
            logger.info("PHASE 7: Sending email via SendGrid...")
            success = mailer.send_email(
                subject=report_data["headline_title"],
                html_content=html_content
            )
            
            if success:
                logger.info("✓ Email sent successfully")
            else:
                logger.error("✗ Email delivery failed")
                return False
        
        # =============================
        # COMPLETION
        # =============================
        logger.info("=" * 60)
        logger.info(f"DAILY BRIEF WORKFLOW COMPLETED - {mode_label}")
        logger.info(f"Run ID: {run_id}")
        logger.info(f"Subject: {report_data['headline_title']}")
        logger.info(f"Artifacts: {run_dir}")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Workflow failed: {e}", exc_info=True)
        return False


def main():
    """
    Main entry point for the daily brief workflow.
    """
    parser = argparse.ArgumentParser(
        description="Daily Markets Brief - End-to-End Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_daily.py              # Full execution with email send
  python run_daily.py --dry-run    # Generate artifacts only, no email
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate artifacts and HTML but do not send email"
    )
    
    args = parser.parse_args()
    
    success = run_daily_workflow(dry_run=args.dry_run)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

import argparse
import sys
import logging
from datetime import datetime

from src.config import Settings
from src.compose import DailyBriefComposer
from src.templates import EmailFormatter
from src.retrieval import RetrievalPlanner
from src.storage import NewsStorage
from src.mailer import NewsMailer
from src.extract import FactCardExtractor
from src.rank import FactCardRanker
from src.logging_utils import setup_logging, save_artifact, cleanup_old_runs

def main():
    parser = argparse.ArgumentParser(description="Automated Markets News Brief")
    parser.add_argument("--type", choices=["daily", "weekly"], required=True, help="Type of report to generate")
    args = parser.parse_args()

    # 1. Configuration & Logging Initialization
    settings = Settings.load()
    run_id, run_dir = setup_logging(settings.app.log_level)
    logger = logging.getLogger(__name__)

    # Cleanup old logs (keep last 7 days)
    cleanup_old_runs(days_to_keep=10)

    logger.info(f"Starting {args.type} markets brief workflow...")

    try:
        # 2. Components Initialization
        planner = RetrievalPlanner(settings)
        composer = DailyBriefComposer(settings)
        formatter = EmailFormatter()
        extractor = FactCardExtractor(settings)
        ranker = FactCardRanker(settings)
        db = NewsStorage(settings.database_path)
        mailer = NewsMailer(settings)

        # 3. Execution based on type
        if args.type == "daily":
            # 3.1 Fetch
            clusters = planner.fetch_and_normalize()
            # Convert objects to dicts for artifact saving
            save_artifact(run_dir, "retrieval_clusters", [c.model_dump() for c in clusters])
            
            if not clusters:
                logger.warning("No news fetched. Skipping brief.")
                return

            # 3.2 Extract Fact Cards
            fact_cards = extractor.extract_fact_cards(clusters)
            save_artifact(run_dir, "extracted_fact_cards", [card.model_dump() for card in fact_cards])
            
            # 3.3 Rank & Bucketize
            buckets = ranker.rank_cards(fact_cards, clusters)
            save_artifact(run_dir, "ranked_buckets", {k: [c.model_dump() for c in v] for k, v in buckets.items()})

            # 3.4 Compose Synthesis from Buckets
            report_raw = composer.compose_daily_brief(buckets)
            
            # Map Markdown to HTML
            report_data = {
                "headline_title": report_raw["headline"],
                "intro_paragraph": report_raw["intro"],
                "top5_html": formatter.md_to_html(report_raw["top5_md"]),
                "macro_html": formatter.md_to_html(report_raw["macro_md"]),
                "watchlist_html": formatter.md_to_html(report_raw["watchlist_md"]),
                "snapshot_html": formatter.md_to_html(report_raw["snapshot_md"]),
                "preheader": report_raw["preheader"]
            }
            save_artifact(run_dir, "brief_composition", report_data)
            
            # 3.5 Persist
            # Store all raw items (primary + supporting) from all clusters
            all_items = []
            for c in clusters:
                all_items.append(c.primary_item.model_dump())
                for s in c.supporting_items:
                    all_items.append(s.model_dump())
            
            db.insert_items(all_items)
            
            # Store extracted fact cards for weekly analysis
            if fact_cards:
                db.insert_fact_cards([card.model_dump() for card in fact_cards])
                logger.info(f"Stored {len(fact_cards)} fact cards for weekly recap.")
            
            now = datetime.now()
            report_id = db.insert_report(
                kind="daily",
                subject=report_data["headline_title"],
                body_html="", # Updated after rendering
                meta=report_data
            )

            # 3.5 Email
            context = {
                "headline_title": report_data["headline_title"],
                "intro_paragraph": report_data["intro_paragraph"],
                "top5_html": report_data["top5_html"],
                "macro_html": report_data["macro_html"],
                "snapshot_html": report_data["snapshot_html"],
                "watchlist_html": report_data["watchlist_html"],
                "preheader": report_data["preheader"],
                "date_label": now.strftime("%A, %b %d, %Y"),
                "generated_time": now.strftime("%H:%M %Z"),
                "archive_url": "#",
                "preferences_url": "#"
            }
            
            html_content = mailer.render_content("email_template.html", context)
            save_artifact(run_dir, "final_email", html_content, extension="html")
            
            # Update report with HTML content
            db.reports.update({'id': report_id, 'body_html': html_content}, ['id'])

            mailer.send_email(
                subject=report_data["headline_title"],
                html_content=html_content
            )

        elif args.type == "weekly":
            logger.info("Weekly recap logic: Summarizing last 7 days.")
            from datetime import timedelta
            
            # Fetch fact cards from the last 7 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
            fact_cards = db.get_fact_cards_between(start_date, end_date)
            
            if not fact_cards:
                logger.warning("No fact cards found for the weekly period. Skipping recap.")
                return

            # Compose weekly synthesis
            report_raw = composer.compose_weekly_recap(fact_cards)
            
            report_data = {
                "headline_title": report_raw["headline"],
                "intro_paragraph": report_raw["intro"],
                "top5_html": formatter.md_to_html(report_raw["top5_md"]),
                "macro_html": formatter.md_to_html(report_raw["macro_md"]),
                "watchlist_html": formatter.md_to_html(report_raw["watchlist_md"]),
                "snapshot_html": formatter.md_to_html(report_raw["snapshot_md"]),
                "preheader": report_raw["preheader"]
            }
            save_artifact(run_dir, "weekly_composition", report_data)
            
            now = datetime.now()
            report_id = db.insert_report(
                kind="weekly",
                subject=report_data["headline_title"],
                body_html="", # Updated after rendering
                meta=report_data
            )

            # Rendering
            context = {
                "headline_title": report_data["headline_title"],
                "intro_paragraph": report_data["intro_paragraph"],
                "top5_html": report_data["top5_html"],
                "macro_html": report_data["macro_html"],
                "snapshot_html": report_data["snapshot_html"],
                "watchlist_html": report_data["watchlist_html"],
                "preheader": report_data["preheader"],
                "date_label": f"Week of {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}",
                "generated_time": now.strftime("%H:%M %Z"),
                "archive_url": "#",
                "preferences_url": "#"
            }
            
            html_content = mailer.render_content("email_template.html", context)
            save_artifact(run_dir, "final_weekly_email", html_content, extension="html")
            
            # Update report with HTML content
            db.reports.update({'id': report_id, 'body_html': html_content}, ['id'])

            mailer.send_email(
                subject=report_data["headline_title"],
                html_content=html_content
            )

        logger.info(f"{args.type.capitalize()} workflow completed successfully.")

    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()




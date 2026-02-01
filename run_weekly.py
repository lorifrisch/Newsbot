#!/usr/bin/env python3
"""
Weekly Markets Recap Workflow
==============================

Orchestrates the weekly recap generation from stored fact cards:
1. Initialize database
2. Query fact cards from the past 7 days
3. Deduplicate by entity (keep highest confidence)
4. Compose weekly analytical recap (OpenAI)
5. Render HTML email
6. Send email (SendGrid)
7. Store artifacts and report metadata

NO PERPLEXITY CALLS - uses existing database content only.

Usage:
    python run_weekly.py              # Full execution with email send
    python run_weekly.py --dry-run    # Generate artifacts only, no send
"""

import argparse
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from src.config import Settings
from src.compose import DailyBriefComposer
from src.templates import EmailFormatter
from src.storage import NewsStorage
from src.mailer import NewsMailer
from src.logging_utils import setup_logging, save_artifact, cleanup_old_runs


def deduplicate_fact_cards(fact_cards: List[Dict]) -> List[Dict]:
    """
    Deduplicate fact cards by entity, keeping the highest confidence score.
    
    Args:
        fact_cards: List of fact card dictionaries from database
        
    Returns:
        Deduplicated list of fact cards
    """
    entity_map = {}
    
    for card in fact_cards:
        entity = card.get('entity', 'Unknown')
        confidence = card.get('confidence', 0.0)
        
        if entity not in entity_map or confidence > entity_map[entity]['confidence']:
            entity_map[entity] = card
    
    return list(entity_map.values())


def run_weekly_workflow(dry_run: bool = False):
    """
    Execute the complete weekly recap workflow.
    
    Args:
        dry_run: If True, generate artifacts and HTML but do not send email.
    """
    
    # =============================
    # PHASE 0: INITIALIZATION
    # =============================
    settings = Settings.load()
    run_id, run_dir = setup_logging(settings.app.log_level)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("WEEKLY RECAP WORKFLOW")
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("=" * 60)
    
    db = NewsStorage(settings.database_path)
    composer = DailyBriefComposer(settings)
    formatter = EmailFormatter()
    mailer = NewsMailer(settings)
    
    # =============================
    # PHASE 1: QUERY DATABASE
    # =============================
    logger.info("\n[PHASE 1] Querying database for past 7 days...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    fact_cards = db.get_fact_cards_between(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )
    
    logger.info(f"Retrieved {len(fact_cards)} fact cards from database")
    
    if not fact_cards:
        logger.warning("No fact cards found in database for past 7 days. Exiting.")
        return
    
    # Save raw fact cards artifact
    save_artifact(run_dir, "1_raw_fact_cards.json", fact_cards)
    
    # =============================
    # PHASE 2: DEDUPLICATE
    # =============================
    logger.info("\n[PHASE 2] Deduplicating fact cards by entity...")
    
    deduped_cards = deduplicate_fact_cards(fact_cards)
    logger.info(f"Deduplicated to {len(deduped_cards)} unique entities")
    
    save_artifact(run_dir, "2_deduped_fact_cards.json", deduped_cards)
    
    # =============================
    # PHASE 3: COMPOSE WEEKLY RECAP
    # =============================
    logger.info("\n[PHASE 3] Composing weekly analytical recap...")
    
    brief = composer.compose_weekly_recap(deduped_cards)
    
    logger.info(f"Composed weekly recap:")
    logger.info(f"  - Theme: {brief.get('theme_of_week', 'N/A')[:60]}...")
    logger.info(f"  - Top developments: {len(brief.get('top_developments', []))}")
    logger.info(f"  - Next week outlook: {brief.get('next_week_outlook', 'N/A')[:60]}...")
    
    save_artifact(run_dir, "3_composed_brief.json", brief)
    
    # =============================
    # PHASE 4: RENDER HTML EMAIL
    # =============================
    logger.info("\n[PHASE 4] Rendering HTML email...")
    
    # Convert markdown sections to HTML
    theme_html = formatter.md_to_html(brief.get('theme_of_week', ''))
    
    top_developments_md = "\n\n".join([
        f"**{i+1}. {dev['headline']}**\n{dev['explanation']}"
        for i, dev in enumerate(brief.get('top_developments', []))
    ])
    top_developments_html = formatter.md_to_html(top_developments_md)
    
    next_week_html = formatter.md_to_html(brief.get('next_week_outlook', ''))
    
    # Render email template
    html_body = formatter.render_weekly_email(
        theme_html=theme_html,
        top_developments_html=top_developments_html,
        next_week_html=next_week_html,
        date_range=f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    )
    
    html_path = run_dir / "4_email.html"
    html_path.write_text(html_body, encoding='utf-8')
    logger.info(f"HTML email saved: {html_path}")
    
    # =============================
    # PHASE 5: STORE REPORT METADATA (moved before email for safety)
    # =============================
    logger.info("\n[PHASE 5] Storing weekly report metadata...")
    
    report_metadata = {
        'run_id': run_id,
        'report_type': 'weekly_recap',
        'date_range_start': start_date.strftime('%Y-%m-%d'),
        'date_range_end': end_date.strftime('%Y-%m-%d'),
        'fact_cards_count': len(deduped_cards),
        'top_developments_count': len(brief.get('top_developments', [])),
        'email_sent': False  # Will be updated if email succeeds
    }
    
    db.save_report_metadata(report_metadata)
    logger.info("Report metadata saved to database")
    
    # =============================
    # PHASE 6: SEND EMAIL
    # =============================
    if dry_run:
        logger.info("\n[PHASE 6] DRY RUN - Skipping email send")
        logger.info(f"Artifacts saved in: {run_dir}")
    else:
        logger.info("\n[PHASE 6] Sending email via SendGrid...")
        
        subject = f"Weekly Markets Recap: {start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}"
        
        success = mailer.send_email(
            subject=subject,
            html_content=html_body
        )
        
        if success:
            logger.info("✅ Email sent successfully")
            # Update metadata to reflect successful email send
            report_metadata['email_sent'] = True
            db.save_report_metadata(report_metadata)
        else:
            logger.error("❌ Email send failed")
            sys.exit(1)
    
    # =============================
    # PHASE 7: CLEANUP
    # =============================
    logger.info("\n[PHASE 7] Cleaning up old runs...")
    cleanup_old_runs(days_to_keep=30)
    
    logger.info("\n" + "=" * 60)
    logger.info("WEEKLY RECAP WORKFLOW COMPLETE")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Weekly Markets Recap Workflow - Database-driven recap generation'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate artifacts and HTML but do not send email'
    )
    
    args = parser.parse_args()
    
    try:
        run_weekly_workflow(dry_run=args.dry_run)
    except Exception as e:
        logging.error(f"Fatal error in weekly workflow: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

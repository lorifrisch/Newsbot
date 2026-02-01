import logging
import dataset
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class NewsStorage:
    """
    Handles SQLite data persistence using the dataset library for 
    news items, fact cards, and generated reports.
    """
    def __init__(self, db_path: str):
        self.db_url = f"sqlite:///{db_path}"
        self.db = dataset.connect(self.db_url)
        self.init_db()

    def init_db(self):
        """
        Initializes the database schema idempotently.
        """
        # items: raw news articles
        self.items = self.db.get_table('items')
        # Create a dummy column to ensure existence before indexing
        if not self.items.columns:
            self.items.insert({'url': 'init'})
            self.items.delete(url='init')
        self.items.create_index(['url'])

        # fact_cards: atomic facts extracted from stories
        self.fact_cards = self.db.get_table('fact_cards')
        if not self.fact_cards.columns:
            self.fact_cards.insert({'story_id': 'init'})
            self.fact_cards.delete(story_id='init')
        self.fact_cards.create_index(['story_id'])

        # reports: generated daily/weekly briefs
        self.reports = self.db.get_table('reports')
        logger.info("Database initialized with tables: items, fact_cards, reports.")


    def insert_items(self, items_list: List[Dict[str, Any]]):
        """
        Inserts or updates news items. Uses 'url' as the unique key.
        """
        try:
            for item in items_list:
                # Ensure tickers_json is stored as a string if it's a list/dict
                if 'tickers_json' in item and not isinstance(item['tickers_json'], str):
                    item['tickers_json'] = json.dumps(item['tickers_json'])
                
                item.setdefault('fetched_at', datetime.now())
                self.items.upsert(item, ['url'])
            logger.info(f"Successfully upserted {len(items_list)} items.")
        except Exception as e:
            logger.error(f"Failed to insert items: {e}")
            raise

    def insert_fact_cards(self, cards: List[Dict[str, Any]]):
        """
        Inserts fact cards. Tries to deduplicate by creating a unique 'hash_id'.
        """
        import hashlib
        try:
            for card in cards:
                # Create a simple unique identifier based on content
                raw_str = f"{card.get('entity')}{card.get('trend')}{card.get('data_point')}"
                hash_id = hashlib.md5(raw_str.encode()).hexdigest()
                card['hash_id'] = hash_id
                
                # SQLite doesn't support lists; convert to JSON strings
                for field in ['tickers', 'sources', 'urls']:
                    if field in card and isinstance(card[field], (list, dict)):
                        card[field] = json.dumps(card[field])
                
                card.setdefault('created_at', datetime.now())
                # Use hash_id to prevent duplicates in the fact_cards table
                self.fact_cards.upsert(card, ['hash_id'])
            logger.info(f"Successfully upserted {len(cards)} fact cards.")
        except Exception as e:
            logger.error(f"Failed to insert fact cards: {e}")
            raise

    def insert_report(self, kind: str, subject: str, body_html: str, meta: Dict[str, Any]) -> int:
        """
        Inserts a generated report into the database.
        """
        try:
            report_id = self.reports.insert({
                'kind': kind, # 'daily' or 'weekly'
                'subject': subject,
                'body_html': body_html,
                'meta_json': json.dumps(meta),
                'created_at': datetime.now()
            })
            logger.info(f"Saved {kind} report with ID: {report_id}")
            return report_id
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            raise

    def save_report_metadata(self, metadata: Dict[str, Any]) -> int:
        """
        Saves report metadata to the database.
        Convenience method that wraps insert_report for metadata-only storage.
        """
        return self.insert_report(
            kind=metadata.get('report_type', 'unknown'),
            subject=f"{metadata.get('report_type', 'Report')} - {metadata.get('run_id', 'N/A')}",
            body_html='',  # HTML stored separately in artifacts
            meta=metadata
        )

    def get_fact_cards_between(self, start_date: datetime, end_date: datetime) -> List[Dict[ Any, Any]]:
        """
        Retrieves fact cards created between two dates for weekly recaps.
        """
        try:
            # dataset doesn't handle complex date filters in find() easily,
            # and raw query string formatting is sensitive. Let's use self.fact_cards.find()
            # with explicit date comparison if possible, or filtered list comprehension
            # as a fallback if the DB driver doesn't support the raw string format.
            all_cards = list(self.fact_cards.all())
            
            filtered = []
            for card in all_cards:
                # dataset often returns dates as datetime objects for SQLite
                created_at = card.get('created_at')
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                
                if created_at and start_date <= created_at <= end_date:
                    if card.get('payload_json'):
                        try:
                            card['payload_json'] = json.loads(card['payload_json'])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    filtered.append(card)
            return filtered
        except Exception as e:
            logger.error(f"Failed to retrieve fact cards between {start_date} and {end_date}: {e}")
            return []


    def delete_obsolete_fact_cards(self, before_date: datetime):
        """
        Deletes fact cards older than the specified date to keep the DB clean.
        """
        try:
            # dataset doesn't have a direct delete with condition easily for dates, so use raw SQL
            query = f"DELETE FROM fact_cards WHERE created_at < '{before_date.isoformat()}'"
            self.db.query(query)
            logger.info(f"Deleted fact cards created before {before_date.isoformat()}.")
        except Exception as e:
            logger.error(f"Failed to delete obsolete fact cards: {e}")
            raise

def init_db(db_path: str) -> NewsStorage:
    return NewsStorage(db_path)



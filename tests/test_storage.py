import os
import pytest
from datetime import datetime, timedelta
from src.storage import NewsStorage

@pytest.fixture
def db():
    # Use a temporary test database
    db_path = "test_news.db"
    storage = NewsStorage(db_path)
    yield storage
    # Cleanup after tests
    if os.path.exists(db_path):
        os.remove(db_path)

def test_insert_items_deduplication(db):
    items = [
        {
            "url": "https://example.com/1",
            "title": "News 1",
            "region": "us",
            "source": "Reuters"
        },
        {
            "url": "https://example.com/1", # Duplicate URL
            "title": "News 1 Updated",
            "region": "us",
            "source": "Reuters"
        }
    ]
    db.insert_items(items)
    
    # Verify only one item exists
    count = db.items.count()
    assert count == 1
    
    # Verify it's the updated one (upsert)
    item = db.items.find_one(url="https://example.com/1")
    assert item['title'] == "News 1 Updated"

def test_fact_card_roundtrip(db):
    cards = [
        {
            "story_id": "story_123",
            "payload_json": {"fact": "Nvidia up 5%", "ticker": "NVDA"}
        }
    ]
    db.insert_fact_cards(cards)
    
    # Retrieve between dates
    now = datetime.now()
    start = now - timedelta(hours=1)
    end = now + timedelta(hours=1)
    
    retrieved = db.get_fact_cards_between(start, end)
    assert len(retrieved) == 1
    assert retrieved[0]['story_id'] == "story_123"
    assert retrieved[0]['payload_json']['ticker'] == "NVDA"

def test_delete_obsolete_cards(db):
    old_date = datetime.now() - timedelta(days=10)
    cards = [
        {
            "story_id": "old_story",
            "created_at": old_date,
            "payload_json": {"fact": "old"}
        },
        {
            "story_id": "new_story",
            "created_at": datetime.now(),
            "payload_json": {"fact": "new"}
        }
    ]
    db.insert_fact_cards(cards)
    
    # Delete cards older than 1 day
    db.delete_obsolete_fact_cards(datetime.now() - timedelta(days=1))
    
    assert db.fact_cards.count() == 1
    assert db.fact_cards.find_one(story_id="new_story") is not None
    assert db.fact_cards.find_one(story_id="old_story") is None

def test_insert_report(db):
    meta = {"top_ticker": "AAPL"}
    report_id = db.insert_report(
        kind="daily",
        subject="Markets Today",
        body_html="<html>test</html>",
        meta=meta
    )
    
    report = db.reports.find_one(id=report_id)
    assert report['kind'] == "daily"
    assert "AAPL" in report['meta_json']

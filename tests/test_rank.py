import pytest
from src.rank import FactCardRanker
from src.extract import FactCard
from src.clustering import StoryCluster
from src.config import Settings
from pydantic import SecretStr

class MockItem:
    def __init__(self, region):
        self.region = region

def test_ranker_us_priority():
    settings = Settings.model_construct(
        watchlist_tickers=[],
        coverage={"US": 0.7, "EU": 0.2, "China": 0.1}
    )
    ranker = FactCardRanker(settings)
    
    # 1. A stronger US story should win over a slightly weaker EU story
    # Test US vs EU priority with sentiment scoring enabled
    # US: confidence 0.95, no regional boost (1.0), positive sentiment boost
    # EU: confidence 0.75, regional boost (1.1), mixed sentiment
    # US should win with higher confidence and positive sentiment
    
    card_us = FactCard(
        story_id="us_major", entity="Fed", trend="Markets rally on dovish pivot", 
        why_it_matters="Bullish signal drives strong gains", confidence=0.95, 
        tickers=[], sources=["Reuters"], urls=["http://reuters.com"]
    )
    cluster_us = StoryCluster(
        cluster_id="us_major", 
        primary_item=MockItem("US"),
        supporting_items=[]
    )
    
    card_eu = FactCard(
        story_id="eu_minor", entity="ECB", trend="Cautious stance", 
        why_it_matters="Uncertainty persists", confidence=0.70, 
        tickers=[], sources=["FT"], urls=["http://ft.com"]
    )
    cluster_eu = StoryCluster(
        cluster_id="eu_minor", 
        primary_item=MockItem("EU"),
        supporting_items=[]
    )
    
    buckets = ranker.rank_cards([card_us, card_eu], [cluster_us, cluster_eu])
    # With larger confidence gap and positive US sentiment, US should win
    assert buckets["top_stories"][0].entity == "Fed"

    # 2. But a high-impact EU story (high volume/confidence) can still make it
    # US (confidence 0.8, items 0) = 0.8
    # EU (confidence 0.9, items 0, multiplier 1.1) = 0.99
    # EU Wins.
    card_us_mid = FactCard(
        story_id="us_mid", entity="US Tech", trend="Steady", 
        why_it_matters="Market momentum", confidence=0.8, 
        tickers=[], sources=["S"], urls=["U"]
    )
    cluster_us_mid = StoryCluster(cluster_id="us_mid", primary_item=MockItem("US"))
    
    card_eu_strong = FactCard(
        story_id="eu_strong", entity="ECB Major", trend="Shock cut", 
        why_it_matters="Policy shift", confidence=0.9, 
        tickers=[], sources=["S"], urls=["U"]
    )
    cluster_eu_strong = StoryCluster(cluster_id="eu_strong", primary_item=MockItem("EU"))

    buckets_2 = ranker.rank_cards([card_us_mid, card_eu_strong], [cluster_us_mid, cluster_eu_strong])
    assert buckets_2["top_stories"][0].entity == "ECB Major"

def test_ranker_global_other_support():
    """Verify that non-core regions (Japan/Taiwan etc) are supported and boosted.
    Sentiment boost is disabled for this test to isolate regional boost behavior.
    """
    from src.config import RankingConfig, SentimentBoostRange
    settings = Settings.model_construct(
        watchlist_tickers=[], 
        coverage={},
        ranking=RankingConfig(use_sentiment_boost=False)  # Disable sentiment for pure regional test
    )
    ranker = FactCardRanker(settings)
    
    # Taiwan Semiconductor story (Global region)
    card_global = FactCard(
        story_id="global_1", entity="TSMC", trend="Production spike", 
        why_it_matters="AI demand", confidence=0.85, 
        tickers=["TSM"], sources=["Nikkei"], urls=["U"]
    )
    cluster_global = StoryCluster(cluster_id="global_1", primary_item=MockItem("GLOBAL"))
    
    # Standard US mid-tier story
    card_us = FactCard(
        story_id="us_1", entity="US Retail", trend="Slight rise", 
        why_it_matters="Economy strength", confidence=0.85, 
        tickers=[], sources=["S"], urls=["U"]
    )
    cluster_us = StoryCluster(cluster_id="us_1", primary_item=MockItem("US"))
    
    buckets = ranker.rank_cards([card_global, card_us], [cluster_global, cluster_us])
    
    # GLOBAL story gets 1.1x boost, so 0.85 * 1.1 = 0.935 > 0.85
    assert buckets["top_stories"][0].entity == "TSMC"

def test_ranker_diversity():
    settings = Settings.model_construct(watchlist_tickers=[], coverage={})
    ranker = FactCardRanker(settings)
    
    # Two stories about NVIDIA
    card1 = FactCard(
        story_id="nv1", entity="NVIDIA", trend="Earnings beat", 
        why_it_matters="AI boom", confidence=0.9, 
        tickers=["NVDA"], sources=["S"], urls=["U"]
    )
    card2 = FactCard(
        story_id="nv2", entity="NVIDIA", trend="New chip launch", 
        why_it_matters="Market lead", confidence=0.85, 
        tickers=["NVDA"], sources=["S"], urls=["U"]
    )
    
    clusters = [
        StoryCluster(cluster_id="nv1", primary_item=MockItem("US")),
        StoryCluster(cluster_id="nv2", primary_item=MockItem("US"))
    ]
    
    buckets = ranker.rank_cards([card1, card2], clusters)
    
    # Only one NVIDIA story should be in top_stories
    assert len(buckets["top_stories"]) == 1
    assert buckets["top_stories"][0].story_id == "nv1"
    # The other should be in company_markets
    assert buckets["company_markets"][0].story_id == "nv2"

def test_macro_detection():
    settings = Settings.model_construct(watchlist_tickers=[], coverage={})
    ranker = FactCardRanker(settings)
    
    macro_card = FactCard(
        story_id="macro", entity="Central Bank", trend="Rate cut", 
        why_it_matters="Stimulus", confidence=0.9, 
        tickers=[], sources=["S"], urls=["U"]
    )
    
    assert ranker._is_macro(macro_card) is True
    
    company_card = FactCard(
        story_id="company", entity="Apple", trend="New iPhone", 
        why_it_matters="Sales", confidence=0.9, 
        tickers=["AAPL"], sources=["S"], urls=["U"]
    )
    
    assert ranker._is_macro(company_card) is False

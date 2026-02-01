import pytest
from src.clustering import cluster_items, jaccard_similarity
from src.retrieval import MarketNewsItem

def test_jaccard_similarity():
    s1 = "Fed signals higher for longer interest rates"
    s2 = "Fed signals higher rates for longer period"
    s3 = "Apple launches new vision pro headset"
    
    sim_12 = jaccard_similarity(s1, s2)
    sim_13 = jaccard_similarity(s1, s3)
    
    assert sim_12 > 0.4
    assert sim_13 < 0.1

def test_clustering_same_story():
    # 3 items about the same story
    item1 = MarketNewsItem(
        title="Nvidia hits record high on AI demand",
        source="Reuters",
        url="https://reuters.com/1",
        published_at="2024-01-01",
        snippet="Short snippet.",
        region="us"
    )
    item2 = MarketNewsItem(
        title="Nvidia stock reaches record high as AI boom continues",
        source="CNBC",
        url="https://cnbc.com/2",
        published_at="2024-01-01",
        snippet="A much longer snippet that should make this the primary item in the cluster.",
        region="us"
    )
    item3 = MarketNewsItem(
        title="Nvidia shares hit record high on AI optimism",
        source="Bloomberg",
        url="https://bloomberg.com/3",
        published_at="2024-01-01",
        snippet="Medium snippet.",
        region="us"
    )
    
    items = [item1, item2, item3]
    clusters = cluster_items(items, jaccard_threshold=0.3)
    
    assert len(clusters) == 1
    cluster = clusters[0]
    
    # Check primary (should be CNBC because of longest snippet)
    assert cluster.primary_item.source == "CNBC"
    # Check supporting (should have max 2 others)
    assert len(cluster.supporting_items) == 2
    sources = [s.source for s in cluster.supporting_items]
    assert "Reuters" in sources
    assert "Bloomberg" in sources

def test_clustering_different_stories():
    item1 = MarketNewsItem(
        title="Fed meeting preview: what to expect",
        source="Reuters",
        url="https://reuters.com/fed",
        published_at="2024-01-01",
        snippet="Snippet A.",
        region="us"
    )
    item2 = MarketNewsItem(
        title="China property crisis deepens with new defaults",
        source="Bloomberg",
        url="https://bloomberg.com/china",
        published_at="2024-01-01",
        snippet="Snippet B.",
        region="china"
    )
    
    items = [item1, item2]
    clusters = cluster_items(items)
    
    assert len(clusters) == 2

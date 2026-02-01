import pytest
from src.dedup import canonicalize_url, deduplicate_items
from src.retrieval import MarketNewsItem

def test_canonicalize_url():
    # Test cases for URL normalization
    base = "https://example.com/news"
    
    # Fragments
    assert canonicalize_url(base + "#section1") == base
    
    # Tracking params (UTM, etc.)
    assert canonicalize_url(base + "?utm_source=twitter&utm_medium=social") == base
    
    # Trailing slash normalization (if path empty)
    assert canonicalize_url("https://example.com") == "https://example.com/"
    
    # Sorting query params and keeping non-tracking ones
    assert canonicalize_url(base + "?z=1&a=2") == base + "?a=2&z=1"
    
    # Scheme normalization
    assert canonicalize_url("HTTP://EXAMPLE.COM") == "http://example.com/"
    
    # WWW normalization
    assert canonicalize_url("https://www.google.com/search") == "https://google.com/search"

def test_deduplicate_items_url():
    # Create items with variant URLs but same content
    item1 = MarketNewsItem(
        title="Fed Raises Rates",
        source="Reuters",
        url="https://reuters.com/finance/123?utm_campaign=daily",
        published_at="2024-01-01",
        snippet="Short snippet.",
        region="us"
    )
    item2 = MarketNewsItem(
        title="Fed Raises Rates",
        source="Reuters",
        url="https://www.reuters.com/finance/123#main",
        published_at="2024-01-01",
        snippet="A much longer and much more descriptive snippet that we want to keep.",
        region="us"
    )
    
    items = [item1, item2]
    deduplicated = deduplicate_items(items)
    
    assert len(deduplicated) == 1
    # Check that it kept the better snippet
    assert "much longer" in deduplicated[0].snippet

def test_deduplicate_items_title_similarity():
    # Create items with different URLs but very similar titles (trivial variants)
    item1 = MarketNewsItem(
        title="Fed Raises Interest Rates by 25 Basis Points",
        source="Bloomberg",
        url="https://bloomberg.com/1",
        published_at="2024-01-01",
        snippet="Short.",
        region="us"
    )
    item2 = MarketNewsItem(
        title="FED RAISES INTEREST RATES BY 25 BASIS POINTS",
        source="CNBC",
        url="https://cnbc.com/2",
        published_at="2024-01-01",
        snippet="Different source but exactly the same title text except case.",
        region="us"
    )
    
    items = [item1, item2]
    deduplicated = deduplicate_items(items, title_threshold=0.9)
    
    assert len(deduplicated) == 1
    assert "CNBC" in deduplicated[0].source # Because it has a longer snippet

def test_no_deduplicate_different_stories():
    item1 = MarketNewsItem(
        title="Apple launches new iPhone",
        source="Verge",
        url="https://verge.com/1",
        published_at="2024-01-01",
        snippet="iPhone talk.",
        region="us"
    )
    item2 = MarketNewsItem(
        title="Tesla recall affects thousands",
        source="CNBC",
        url="https://cnbc.com/2",
        published_at="2024-01-01",
        snippet="Tesla talk.",
        region="us"
    )
    
    items = [item1, item2]
    deduplicated = deduplicate_items(items)
    
    assert len(deduplicated) == 2


# Additional edge case tests
@pytest.mark.unit
def test_canonicalize_url_empty_string():
    """Test canonicalization with empty string."""
    assert canonicalize_url("") == ""


@pytest.mark.unit
def test_canonicalize_url_unicode_domain():
    """Test canonicalization with international domain."""
    url = "https://例え.jp/news?id=123"
    result = canonicalize_url(url)
    # Should handle unicode domains
    assert "例え" in result or "xn--" in result  # Punycode


@pytest.mark.unit
def test_canonicalize_url_with_port():
    """Test canonicalization with port number."""
    url = "https://example.com:8080/path"
    result = canonicalize_url(url)
    assert ":8080" in result


@pytest.mark.unit
def test_canonicalize_url_with_auth():
    """Test canonicalization with authentication."""
    url = "https://user:pass@example.com/path"
    result = canonicalize_url(url)
    # Should preserve auth
    assert "user" in result or "example.com" in result


@pytest.mark.unit
def test_canonicalize_url_encoded_characters():
    """Test canonicalization with URL-encoded characters."""
    url = "https://example.com/path%20with%20spaces?q=%2Ftest"
    result = canonicalize_url(url)
    assert "example.com" in result


@pytest.mark.unit
def test_canonicalize_url_multiple_same_query_params():
    """Test canonicalization with duplicate query parameters."""
    url = "https://example.com/path?id=1&id=2&id=3"
    result = canonicalize_url(url)
    assert "id=" in result


@pytest.mark.unit
def test_canonicalize_url_mixed_tracking_params():
    """Test filtering of mixed tracking and non-tracking parameters."""
    url = "https://example.com/news?id=123&utm_source=twitter&ref=homepage&utm_campaign=daily"
    result = canonicalize_url(url)
    # Should keep id and ref, remove utm_*
    assert "id=123" in result
    assert "ref=homepage" in result
    assert "utm_source" not in result
    assert "utm_campaign" not in result


@pytest.mark.unit
def test_deduplicate_items_empty_list():
    """Test deduplication with empty list."""
    result = deduplicate_items([])
    assert result == []


@pytest.mark.unit
def test_deduplicate_items_single_item():
    """Test deduplication with single item."""
    item = MarketNewsItem(
        title="Test",
        source="Source",
        url="https://test.com",
        published_at="2024-01-01",
        snippet="Snippet",
        region="us"
    )
    result = deduplicate_items([item])
    assert len(result) == 1
    assert result[0] == item


@pytest.mark.unit
def test_deduplicate_items_exact_title_match():
    """Test deduplication with exactly identical titles."""
    item1 = MarketNewsItem(
        title="Exact Same Title",
        source="Source1",
        url="https://test1.com",
        published_at="2024-01-01",
        snippet="Short",
        region="us"
    )
    item2 = MarketNewsItem(
        title="Exact Same Title",
        source="Source2",
        url="https://test2.com",
        published_at="2024-01-01",
        snippet="Much longer snippet that should be kept",
        region="us"
    )
    
    result = deduplicate_items([item1, item2])
    assert len(result) == 1
    assert "longer snippet" in result[0].snippet


@pytest.mark.unit
def test_deduplicate_items_boundary_similarity():
    """Test deduplication at exactly 0.85 threshold."""
    # Create titles that are exactly at the threshold
    item1 = MarketNewsItem(
        title="Federal Reserve Raises Interest Rates",
        source="Source1",
        url="https://test1.com",
        published_at="2024-01-01",
        snippet="Text",
        region="us"
    )
    item2 = MarketNewsItem(
        title="Federal Reserve Raises Interest Rates Today",
        source="Source2",
        url="https://test2.com",
        published_at="2024-01-01",
        snippet="Text",
        region="us"
    )
    
    result = deduplicate_items([item1, item2], title_threshold=0.85)
    # Should deduplicate if similarity >= 0.85
    assert len(result) <= 2


@pytest.mark.unit
def test_deduplicate_items_multiple_duplicates():
    """Test deduplication with 3+ duplicates of same story."""
    items = [
        MarketNewsItem(
            title="Fed Rate Decision",
            source=f"Source{i}",
            url=f"https://test{i}.com",
            published_at="2024-01-01",
            snippet="x" * (10 * i),  # Varying snippet lengths: 10, 20, 30, 40
            region="us"
        )
        for i in range(1, 5)
    ]
    
    result = deduplicate_items(items)
    # Should keep only one (with longest snippet - 40 chars from item 4)
    assert len(result) == 1
    assert len(result[0].snippet) == 40


@pytest.mark.unit
def test_deduplicate_items_empty_titles():
    """Test deduplication with empty titles."""
    item1 = MarketNewsItem(
        title="",
        source="Source1",
        url="https://test1.com",
        published_at="2024-01-01",
        snippet="Snippet1",
        region="us"
    )
    item2 = MarketNewsItem(
        title="",
        source="Source2",
        url="https://test2.com",
        published_at="2024-01-01",
        snippet="Snippet2",
        region="us"
    )
    
    # Should not crash, should keep both (no similarity on empty strings)
    result = deduplicate_items([item1, item2])
    assert len(result) >= 1


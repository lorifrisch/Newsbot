import logging
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from difflib import SequenceMatcher
from typing import List, Any

logger = logging.getLogger(__name__)

# Common tracking parameters to strip
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'gclid', 'fbclid', 'mc_cid', 'mc_eid', '_hsenc', '_hsmi', 'mkt_tok'
}

def canonicalize_url(url: str) -> str:
    """
    Normalizes a URL by:
    1. Lowercasing the scheme and host.
    2. Removing common tracking parameters (UTM, etc.).
    3. Removing URL fragments.
    4. Sorting remaining query parameters.
    5. Ensuring a trailing slash for empty paths if host is present.
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url)
        # Normalize scheme and netloc (domain)
        scheme = parsed.scheme.lower()
        
        # Optionally force https if desired, but for now just normalize
        netloc = parsed.netloc.lower()
        
        # Remove 'www.' from domain for broader matching
        if netloc.startswith('www.'):
            netloc = netloc[4:]
            
        path = parsed.path
        if not path and netloc:
            path = '/'
            
        # Strip tracking parameters and sort remaining for consistency
        query_params = parse_qsl(parsed.query)
        filtered_params = sorted([
            (k, v) for k, v in query_params 
            if k.lower() not in TRACKING_PARAMS
        ])
        
        new_query = urlencode(filtered_params)
        
        # Reconstruct URL without fragment
        return urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
    except Exception as e:
        logger.warning(f"Failed to canonicalize URL '{url}': {e}")
        return url

def get_title_similarity(a: str, b: str) -> float:
    """
    Returns a similarity ratio between two titles (case-insensitive).
    """
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def deduplicate_items(items: List[Any], title_threshold: float = 0.85) -> List[Any]:
    """
    Deduplicates a list of news items based on canonical URL and title similarity.
    Preserves the item with the longest snippet when a duplicate is found.
    
    Expects items to have at least: .url, .title, .snippet
    """
    unique_items = []
    seen_canonical_urls = {} # canonical_url -> index in unique_items
    
    for item in items:
        canon_url = canonicalize_url(item.url)
        is_duplicate = False
        
        # 1. Exact canonical URL match
        if canon_url in seen_canonical_urls:
            idx = seen_canonical_urls[canon_url]
            # Keep the one with the longer snippet
            if len(item.snippet) > len(unique_items[idx].snippet):
                unique_items[idx] = item
            is_duplicate = True
            
        # 2. Fuzzy title match against already added unique items
        if not is_duplicate:
            for idx, existing in enumerate(unique_items):
                if get_title_similarity(item.title, existing.title) > title_threshold:
                    # Duplicate found via title
                    # Keep the one with the longer snippet
                    if len(item.snippet) > len(unique_items[idx].snippet):
                        unique_items[idx] = item
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            seen_canonical_urls[canon_url] = len(unique_items)
            unique_items.append(item)
            
    return unique_items

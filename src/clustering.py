import logging
import hashlib
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from src.dedup import canonicalize_url, get_title_similarity

logger = logging.getLogger(__name__)

class StoryCluster(BaseModel):
    """
    Groups multiple items about the same story.
    """
    cluster_id: str
    primary_item: Any  # Usually a MarketNewsItem
    supporting_items: List[Any] = []

    def add_item(self, item: Any, max_supporting: int = 2):
        if len(self.supporting_items) < max_supporting:
            # Check if this new item has a better (longer) snippet than primary
            if len(item.snippet) > len(self.primary_item.snippet):
                # Swap out primary
                old_primary = self.primary_item
                self.primary_item = item
                # Add old primary to supporting if there is space
                if len(self.supporting_items) < max_supporting:
                    self.supporting_items.append(old_primary)
            else:
                self.supporting_items.append(item)

def tokenize(text: str) -> set:
    """
    Simple tokenizer: lowercase, removes non-alphanumeric, split by whitespace.
    """
    # Remove common financial noise/punctuation
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())
    # Keep 'ai', 'us', 'eu', 'fed' - common financial tokens that are short
    tokens = {w for w in clean.split() if len(w) > 2 or w in {'ai', 'us', 'eu', 'fed'}}
    return tokens

def jaccard_similarity(a: str, b: str) -> float:
    """
    Returns Jaccard similarity between two strings based on tokens.
    Intersection over Union.
    """
    set_a = tokenize(a)
    set_b = tokenize(b)
    
    if not set_a or not set_b:
        return 0.0
        
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    
    return intersection / union

def cluster_items(
    items: List[Any], 
    url_dedup: bool = True,
    title_threshold: float = 0.85, 
    jaccard_threshold: float = 0.45,
    max_supporting: int = 2
) -> List[StoryCluster]:
    """
    Groups items into clusters based on URL canonicalization and title similarity.
    """
    clusters: List[StoryCluster] = []
    
    # Pre-calculate canonical URLs for exact match speed if requested
    canon_map = {}
    if url_dedup:
        for item in items:
            canon = canonicalize_url(item.url)
            canon_map[item.url] = canon

    for item in items:
        found_cluster = False
        item_canon_url = canon_map.get(item.url) if url_dedup else None
        
        for cluster in clusters:
            # Match 1: Canonical URL Match
            if url_dedup:
                cluster_urls = [canon_map.get(cluster.primary_item.url)] + \
                              [canon_map.get(s.url) for s in cluster.supporting_items]
                if item_canon_url in cluster_urls:
                    cluster.add_item(item, max_supporting)
                    found_cluster = True
                    break
            
            # Match 2: SequenceMatcher Title Match (High precision for variants)
            if get_title_similarity(item.title, cluster.primary_item.title) > title_threshold:
                cluster.add_item(item, max_supporting)
                found_cluster = True
                break
                
            # Match 3: Jaccard Similarity (Better for "same story, different source" phrasing)
            if jaccard_similarity(item.title, cluster.primary_item.title) > jaccard_threshold:
                cluster.add_item(item, max_supporting)
                found_cluster = True
                break

        if not found_cluster:
            # Create a new cluster
            cluster_id = hashlib.md5(f"{item.title}{item.url}".encode()).hexdigest()
            new_cluster = StoryCluster(
                cluster_id=cluster_id,
                primary_item=item,
                supporting_items=[]
            )
            clusters.append(new_cluster)
            
    return clusters

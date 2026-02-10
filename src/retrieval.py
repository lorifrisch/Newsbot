import logging
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, HttpUrl, validator

from src.config import Settings
from src.perplexity_client import PerplexityClient
from src.dedup import canonicalize_url
from src.clustering import cluster_items, StoryCluster

logger = logging.getLogger(__name__)

@dataclass
class RetrievalResult:
    """
    Tracks retrieval success/failure and provides metadata about the operation.
    """
    clusters: List[StoryCluster]
    successful_queries: int
    failed_queries: int
    query_details: Dict[str, bool] = field(default_factory=dict)  # query_name -> success
    is_sufficient: bool = field(default=True)  # At least 3/6 queries succeeded
    # Additional metrics for quality tracking
    items_by_region: Dict[str, int] = field(default_factory=dict)
    items_by_query: Dict[str, int] = field(default_factory=dict)
    watchlist_tickers_covered: List[str] = field(default_factory=list)
    items_dropped_no_url: int = 0
    
    def __post_init__(self):
        # Auto-calculate is_sufficient if not already set
        if self.successful_queries < 3:
            self.is_sufficient = False

class MarketNewsItem(BaseModel):
    """
    Normalized schema for a single news item.
    """
    title: str
    source: str
    url: str
    published_at: str
    snippet: str
    region: str # 'us', 'eu', 'china', 'watchlist', 'global', 'other'
    canonical_url: Optional[str] = None

    @validator('url')
    def validate_url(cls, v):
        # Basic URL validation if HttpUrl isn't strict enough or for easier handling
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Invalid URL scheme')
        return v
    
    @validator('canonical_url', always=True)
    def set_canonical_url(cls, v, values):
        if not v and 'url' in values:
            return canonicalize_url(values['url'])
        return v

class RetrievalPlanner:
    """
    Executes a multi-query daily retrieval plan and normalizes results.
    Supports domain allowlist filtering for quality control.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.perplexity = PerplexityClient(settings)
        self.daily_config = settings.daily
        
        # Domain allowlist from config (empty = allow all)
        retrieval_config = getattr(settings, 'retrieval', None)
        self.allowed_domains = getattr(retrieval_config, 'allowed_domains', []) if retrieval_config else []
        if self.allowed_domains:
            logger.info(f"Domain allowlist enabled: {len(self.allowed_domains)} domains")

    def _is_domain_allowed(self, url: str) -> bool:
        """Check if URL's domain is in the allowlist (if configured)."""
        if not self.allowed_domains:
            return True  # No allowlist = allow all
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix for matching
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Check if domain matches any allowed domain
            for allowed in self.allowed_domains:
                allowed_lower = allowed.lower()
                if allowed_lower.startswith('www.'):
                    allowed_lower = allowed_lower[4:]
                if domain == allowed_lower or domain.endswith('.' + allowed_lower):
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error checking domain for {url}: {e}")
            return True  # Allow on error to avoid dropping valid content

    def _get_system_prompt(self) -> str:
        snippet_limit = self.daily_config.snippet_words
        return f"""You are a professional financial news aggregator. 
You must return a raw JSON array of objects. Each object must have:
- title: clear, concise headline
- source: name of the news outlet
- url: full valid URL to the article
- published_at: ISO 8601 date string
- snippet: summary capped at {snippet_limit} words
- region: categorical tag as requested in the query

Return ONLY the JSON array. Do not include markdown formatting or preamble."""

    def _generate_queries(self) -> Dict[str, str]:
        """
        Defines the multi-query daily retrieval plan.
        Updated to request more items per query to ensure regional coverage.
        BUGFIX: Split watchlist into batched queries (3 tickers per query) for better coverage.
        """
        items_per_query = self.daily_config.max_candidates_per_query
        
        queries = {
            "us_macro": f"Top {items_per_query} US macro and policy news today (Fed, inflation, employment, Treasury, fiscal policy). Include source URLs. Region tag: 'us'",
            "us_equities": f"Top {items_per_query} US equity market movers, sector trends, and major earnings today. Include source URLs. Region tag: 'us'",
            "eu_market": f"Top {items_per_query} Eurozone macro news, ECB policy, and major European stock market movers today. Include source URLs. Region tag: 'eu'",
            "china_market": f"Top {items_per_query} news on China macro, tech regulation, property market, and PBOC policy today. Include source URLs. Region tag: 'china'",
            "global_market": f"Top {items_per_query} market-moving news from Japan (Yen, Nikkei, BOJ), SE Asia (TSMC, semiconductors), and Latin America (EM trends). Include source URLs. Region tag: 'global'"
        }
        
        # BUGFIX: Batch watchlist tickers into groups of 3 for better coverage
        # Each query requests 2-3 items per ticker to ensure every ticker gets news
        watchlist_tickers = self.settings.watchlist_tickers if self.settings.watchlist_tickers else []
        batch_size = 3
        
        for i in range(0, len(watchlist_tickers), batch_size):
            batch = watchlist_tickers[i:i+batch_size]
            batch_name = f"watchlist_batch_{(i//batch_size) + 1}"
            tickers_str = ", ".join(batch)
            queries[batch_name] = f"Latest 2-3 news items for EACH of these tickers: {tickers_str}. Include source URLs for each story. Region tag: 'watchlist'"
        
        return queries
    
    def _generate_fallback_watchlist_query(self, uncovered_tickers: List[str]) -> str:
        """Generate a targeted query for uncovered watchlist tickers."""
        tickers_str = ", ".join(uncovered_tickers)
        return f"Latest news and developments for these specific tickers: {tickers_str}. Include source URLs for each story. Region tag: 'watchlist'"

    def fetch_and_normalize(self) -> RetrievalResult:
        """
        Runs the multi-query plan, clusters items about the same story, and enforces regional balance.
        Returns a RetrievalResult with success/failure tracking.
        Implements circuit breaker: fails fast after 2 consecutive query failures.
        Requires minimum 3/6 successful queries.
        Includes fallback mechanism for insufficient watchlist coverage.
        """
        queries = self._generate_queries()
        all_candidates: List[MarketNewsItem] = []
        
        # Tracking variables
        successful_queries = 0
        failed_queries = 0
        query_details = {}
        consecutive_failures = 0
        max_consecutive_failures = 2
        domain_filtered_count = 0
        items_dropped_no_url = 0
        
        # Items per query tracking
        items_by_query = {}
        
        # Watchlist ticker tracking
        watchlist_tickers = [t.upper() for t in self.settings.watchlist_tickers]
        tickers_found_in_items = set()

        for key, query in queries.items():
            logger.info(f"Executing retrieval query for {key}...")
            try:
                raw_response = self.perplexity.chat(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": query}
                    ],
                    temperature=0.1 # Low temperature for consistent JSON
                )
                
                items = self._parse_json_items(raw_response)
                items_by_query[key] = 0
                
                # Track snippet truncation
                truncated_count = 0
                for item in items:
                    try:
                        # Validate URL exists
                        url = item.get('url', '')
                        if not url or not url.startswith(('http://', 'https://')):
                            items_dropped_no_url += 1
                            logger.debug(f"Dropped item without valid URL: {item.get('title', 'unknown')[:50]}")
                            continue
                        
                        # Domain allowlist filtering
                        if not self._is_domain_allowed(url):
                            domain_filtered_count += 1
                            logger.debug(f"Filtered out item from non-allowed domain: {url}")
                            continue
                        
                        # Normalize snippet length just in case
                        words = item.get('snippet', '').split()
                        if len(words) > self.daily_config.snippet_words:
                            item['snippet'] = " ".join(words[:self.daily_config.snippet_words]) + "..."
                            truncated_count += 1
                        
                        news_item = MarketNewsItem(**item)
                        all_candidates.append(news_item)
                        items_by_query[key] = items_by_query.get(key, 0) + 1
                        
                        # Track watchlist tickers found
                        title_upper = news_item.title.upper()
                        snippet_upper = news_item.snippet.upper()
                        for ticker in watchlist_tickers:
                            if ticker in title_upper or ticker in snippet_upper:
                                tickers_found_in_items.add(ticker)
                        
                    except Exception as ve:
                        logger.warning(f"Skipping invalid item: {ve}")
                
                if truncated_count > 0:
                    logger.info(f"Truncated {truncated_count} snippets in {key} to {self.daily_config.snippet_words} words")
                
                # Success!
                successful_queries += 1
                query_details[key] = True
                consecutive_failures = 0  # Reset circuit breaker
                logger.info(f"Query {key} succeeded with {items_by_query.get(key, 0)} valid items")

            except Exception as e:
                failed_queries += 1
                query_details[key] = False
                consecutive_failures += 1
                logger.error(f"Query {key} failed: {e}")
                
                # Circuit breaker: fail fast after 2 consecutive failures
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(
                        f"Circuit breaker triggered: {consecutive_failures} consecutive failures. "
                        f"Stopping further queries to save time/costs."
                    )
                    # Mark remaining queries as failed
                    remaining_keys = [k for k in queries.keys() if k not in query_details]
                    for remaining_key in remaining_keys:
                        query_details[remaining_key] = False
                        failed_queries += 1
                    break

        # Log domain filtering stats
        if domain_filtered_count > 0:
            logger.info(f"Domain allowlist filtered out {domain_filtered_count} items from non-allowed domains")
        if items_dropped_no_url > 0:
            logger.info(f"Dropped {items_dropped_no_url} items without valid URLs")

        # Fallback: Check watchlist coverage and run additional query if needed
        uncovered_tickers = [t for t in watchlist_tickers if t not in tickers_found_in_items]
        min_tickers_required = self.daily_config.min_watchlist_tickers_covered
        
        if len(uncovered_tickers) > (len(watchlist_tickers) - min_tickers_required) and uncovered_tickers:
            logger.info(f"Watchlist coverage insufficient: {len(tickers_found_in_items)}/{len(watchlist_tickers)} tickers. Running fallback query for: {uncovered_tickers}")
            try:
                fallback_query = self._generate_fallback_watchlist_query(uncovered_tickers)
                raw_response = self.perplexity.chat(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": fallback_query}
                    ],
                    temperature=0.1
                )
                items = self._parse_json_items(raw_response)
                fallback_added = 0
                for item in items:
                    try:
                        url = item.get('url', '')
                        if not url or not url.startswith(('http://', 'https://')):
                            continue
                        if not self._is_domain_allowed(url):
                            continue
                        news_item = MarketNewsItem(**item)
                        all_candidates.append(news_item)
                        fallback_added += 1
                        # Update ticker tracking
                        title_upper = news_item.title.upper()
                        snippet_upper = news_item.snippet.upper()
                        for ticker in uncovered_tickers:
                            if ticker in title_upper or ticker in snippet_upper:
                                tickers_found_in_items.add(ticker)
                    except Exception as ve:
                        logger.warning(f"Skipping invalid fallback item: {ve}")
                logger.info(f"Fallback watchlist query added {fallback_added} items")
                items_by_query["watchlist_fallback"] = fallback_added
            except Exception as e:
                logger.warning(f"Fallback watchlist query failed: {e}")

        # Calculate items by region
        items_by_region = {}
        for item in all_candidates:
            region = item.region.lower()
            items_by_region[region] = items_by_region.get(region, 0) + 1
        
        # Log regional coverage
        logger.info(f"Items by region: {items_by_region}")
        
        # Check if we need additional queries for regions below minimum
        min_us = self.daily_config.min_us_items
        min_eu = self.daily_config.min_eu_items
        min_china = self.daily_config.min_china_items
        
        if items_by_region.get('us', 0) < min_us:
            logger.warning(f"US coverage below minimum: {items_by_region.get('us', 0)} < {min_us}")
        if items_by_region.get('eu', 0) < min_eu:
            logger.warning(f"EU coverage below minimum: {items_by_region.get('eu', 0)} < {min_eu}")
        if items_by_region.get('china', 0) < min_china:
            logger.warning(f"China coverage below minimum: {items_by_region.get('china', 0)} < {min_china}")

        # Clustered items (each cluster has a primary + optional supporting)
        clusters = cluster_items(all_candidates)
        logger.info(
            f"Retrieval complete: {successful_queries}/{len(queries)} queries succeeded, "
            f"{failed_queries} failed. Grouped {len(all_candidates)} items into {len(clusters)} clusters."
        )
        
        # Check minimum threshold
        is_sufficient = successful_queries >= 3
        if not is_sufficient:
            logger.warning(
                f"Insufficient retrieval: only {successful_queries}/6 queries succeeded. "
                f"Minimum threshold is 3/6. Report quality may be degraded."
            )
        
        final_clusters = self._merge_and_cap_clusters(clusters)
        
        return RetrievalResult(
            clusters=final_clusters,
            successful_queries=successful_queries,
            failed_queries=failed_queries,
            query_details=query_details,
            is_sufficient=is_sufficient,
            items_by_region=items_by_region,
            items_by_query=items_by_query,
            watchlist_tickers_covered=list(tickers_found_in_items),
            items_dropped_no_url=items_dropped_no_url
        )

    def _parse_json_items(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Extracts JSON array from Perplexity response text.
        """
        try:
            # Clean up potential markdown code blocks
            clean_text = re.sub(r'```json\n?|\n?```', '', raw_text).strip()
            # If there's still preamble, try to find the first '[' and last ']'
            start = clean_text.find('[')
            end = clean_text.rfind(']')
            if start != -1 and end != -1:
                clean_text = clean_text[start:end+1]
            
            data = json.loads(clean_text)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to parse JSON from Perplexity: {e}")
            return []

    def _merge_and_cap_clusters(self, clusters: List[StoryCluster]) -> List[StoryCluster]:
        """
        Enforces max_candidates and regional fallback for clusters.
        """
        max_total = self.daily_config.max_candidates
        
        # Group clusters by the regional tag of their PRIMARY item
        by_region = {
            'us': [c for c in clusters if c.primary_item.region == 'us'],
            'eu': [c for c in clusters if c.primary_item.region == 'eu'],
            'china': [c for c in clusters if c.primary_item.region == 'china'],
            'global': [c for c in clusters if c.primary_item.region == 'global'],
            'watchlist': [c for c in clusters if c.primary_item.region == 'watchlist'],
            'other': [c for c in clusters if c.primary_item.region not in ['us', 'eu', 'china', 'watchlist', 'global']]
        }

        final_list = []
        
        # Priority 1: Watchlist
        final_list.extend(by_region['watchlist'][:3])
        
        # Priority 2: CORE Targeted Regions
        # We still maintain a loose target for the core regions
        us_target = int(max_total * 0.6) # Shifted slightly down to allow global
        eu_target = int(max_total * 0.1)
        china_target = int(max_total * 0.1)
        
        final_list.extend(by_region['us'][:us_target])
        final_list.extend(by_region['eu'][:eu_target])
        final_list.extend(by_region['china'][:china_target])
        
        # Priority 3: Global & Rest of the world fillers
        # This allows Yen news, LATAM news etc to fill the remaining 20% + gaps
        remaining_slots = max_total - len(final_list)
        if remaining_slots > 0:
            # Sort remaining potential by some importance if possible, here just use existing order
            # which is based on query-specific rankings from Perplexity.
            pool = [c for c in clusters if c not in final_list]
            final_list.extend(pool[:remaining_slots])
            
        return final_list[:max_total]

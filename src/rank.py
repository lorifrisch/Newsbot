import logging
from typing import List, Dict, Set, Optional
from src.config import Settings
from src.extract import FactCard
from src.clustering import StoryCluster

logger = logging.getLogger(__name__)

# Lazy import sentiment to avoid slow startup if NLTK not installed
_sentiment_analyzer = None


def _get_sentiment_analyzer():
    """Lazy load sentiment analyzer."""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        try:
            from src.sentiment import SentimentAnalyzer
            _sentiment_analyzer = SentimentAnalyzer()
        except ImportError:
            logger.debug("Sentiment analysis not available")
            _sentiment_analyzer = False  # Mark as unavailable
    return _sentiment_analyzer if _sentiment_analyzer else None

class FactCardRanker:
    """
    Ranks and categorizes FactCards into structural sections for the brief.
    Identifies Watchlist items, Top Stories, Macro updates, and general Market news.
    Enforces coverage constraints: US, EU, China representation in Top 5.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.watchlist = [t.upper() for t in settings.watchlist_tickers]
        self.coverage_weights = settings.coverage or {"US": 0.7, "EU": 0.2, "China": 0.1}
        
        # Sentiment boost configuration
        self.use_sentiment_boost = getattr(settings.ranking, 'use_sentiment_boost', True)
        boost_range = getattr(settings.ranking, 'sentiment_boost_range', None)
        if boost_range:
            self.sentiment_boost_min = getattr(boost_range, 'min', 0.95)
            self.sentiment_boost_max = getattr(boost_range, 'max', 1.15)
        else:
            self.sentiment_boost_min = 0.95
            self.sentiment_boost_max = 1.15
        
        # Coverage constraints
        self.require_us_in_top5 = getattr(settings.ranking, 'require_us_in_top5', True)
        self.require_eu_in_top5 = getattr(settings.ranking, 'require_eu_in_top5', True)
        self.require_china_in_top5 = getattr(settings.ranking, 'require_china_in_top5', True)
        
        # Analyst target filtering
        self.deprioritize_analyst_targets = getattr(settings.ranking, 'deprioritize_analyst_targets', True)
        self.analyst_target_keywords = getattr(settings.ranking, 'analyst_target_keywords', [
            "price target", "analyst rating", "upgraded", "downgraded", "initiated coverage"
        ])
        
        # Refined macro keywords for heuristic categorization
        self.macro_keywords = {
            "fed", "fomc", "central bank", "ecb", "boj", "pboc", "interest rates", 
            "inflation", "cpi", "pce", "gdp", "growth", "recession", "stimulus", 
            "monetary policy", "fiscal policy", "treasury", "yield curve", "employment",
            "unemployment", "payroll", "labor market", "deficit", "debt ceiling",
            "quantitative easing", "tightening", "hawkish", "dovish", "rate hike", 
            "rate cut", "trade balance", "retail sales", "consumer spending"
        }
    
    def _is_analyst_target_story(self, card: FactCard) -> bool:
        """Check if a card is primarily about analyst price targets."""
        combined_text = (card.entity + " " + card.trend + " " + (card.why_it_matters or "")).lower()
        return any(kw in combined_text for kw in self.analyst_target_keywords)
    
    def _get_card_region(self, card: FactCard, id_to_cluster: Dict) -> str:
        """Determine the region of a card based on its cluster."""
        cluster = id_to_cluster.get(card.story_id)
        if cluster:
            return getattr(cluster.primary_item, 'region', 'other').upper()
        # Fallback: infer from content
        combined_text = (card.entity + " " + card.trend).lower()
        if any(kw in combined_text for kw in ["china", "chinese", "pboc", "shanghai", "hong kong"]):
            return "CHINA"
        if any(kw in combined_text for kw in ["europe", "euro", "ecb", "germany", "france", "uk", "london"]):
            return "EU"
        return "US"

    def rank_cards(self, cards: List[FactCard], clusters: List[StoryCluster]) -> Dict[str, List[FactCard]]:
        """
        Groups cards into top_stories, macro_policy, company_markets, and watchlist.
        Implements regional balancing, entity diversity, sentiment weighting, and coverage constraints.
        
        Coverage constraints:
        - Top 5 must include at least 1 US macro/policy item (if available)
        - Top 5 must include at least 1 EU item (if available)
        - Top 5 must include at least 1 China item (if available) OR flag for "no China" note
        - Analyst price targets are deprioritized
        """
        if not cards:
            return {
                "top_stories": [],
                "macro_policy": [],
                "company_markets": [],
                "watchlist": [],
                "sentiment_summary": None,
                "china_news_available": False,
                "china_note_needed": True
            }

        # Map for cluster lookup to get supporting items count and region
        id_to_cluster = {c.cluster_id: c for c in clusters}
        
        # Get sentiment analyzer (may be None if NLTK not installed or disabled)
        sentiment_analyzer = _get_sentiment_analyzer() if self.use_sentiment_boost else None
        
        # Capture boost range for use in calculate_score
        boost_min = self.sentiment_boost_min
        boost_max = self.sentiment_boost_max
        
        # Pre-calculate regions for all cards
        card_regions = {id(card): self._get_card_region(card, id_to_cluster) for card in cards}
        
        # Scoring logic with sentiment integration
        def calculate_score(card: FactCard) -> float:
            cluster = id_to_cluster.get(card.story_id)
            if not cluster:
                return card.confidence
                
            # Base score from confidence
            score = card.confidence
            
            # Boost from volume of coverage (supporting items)
            supporting_count = len(cluster.supporting_items)
            score *= (1 + (supporting_count * 0.15))
            
            # Regional balancing: US is the main focus (baseline).
            # Other regions get a subtle 10% "participation boost"
            region = card_regions.get(id(card), "US")
            if region != "US":
                score *= 1.10
            
            # Deprioritize analyst price target stories
            if self.deprioritize_analyst_targets and self._is_analyst_target_story(card):
                score *= 0.7  # 30% penalty
            
            # Sentiment boost: extreme sentiment = more newsworthy
            if sentiment_analyzer:
                sentiment_boost = sentiment_analyzer.get_sentiment_boost(
                    card, 
                    boost_min=boost_min, 
                    boost_max=boost_max
                )
                score *= sentiment_boost
            
            return score

        # Pre-calculate scores
        scored_cards = []
        for card in cards:
            scored_cards.append({
                "card": card,
                "score": calculate_score(card),
                "region": card_regions.get(id(card), "US"),
                "is_analyst_target": self._is_analyst_target_story(card)
            })
            
        # Sort by score descending
        scored_cards.sort(key=lambda x: x["score"], reverse=True)
        
        # Track available cards by region for coverage constraints
        cards_by_region = {"US": [], "EU": [], "CHINA": [], "GLOBAL": [], "OTHER": []}
        for sc in scored_cards:
            region = sc["region"]
            if region in cards_by_region:
                cards_by_region[region].append(sc)
            else:
                cards_by_region["OTHER"].append(sc)
        
        # Check China news availability
        china_news_available = len(cards_by_region.get("CHINA", [])) > 0
        
        buckets = {
            "watchlist": [],
            "top_stories": [],
            "macro_policy": [],
            "company_markets": []
        }
        
        used_entities: Set[str] = set()
        used_card_ids: Set[int] = set()
        
        # Phase 1: Extract watchlist items first (they can appear in BOTH watchlist AND top stories)
        watchlist_cards = []
        for sc in scored_cards:
            card = sc["card"]
            card_tickers = [t.upper() for t in card.tickers]
            if any(t in self.watchlist for t in card_tickers):
                watchlist_cards.append(sc)
                buckets["watchlist"].append(card)
        
        # Phase 2: Build Top 5 with coverage constraints
        # Reserve slots: 1 for EU (if available), 1 for China (if available)
        eu_slot_filled = False
        china_slot_filled = False
        us_macro_slot_filled = False
        
        # First pass: Fill reserved slots
        if self.require_eu_in_top5 and cards_by_region.get("EU"):
            for sc in cards_by_region["EU"]:
                if id(sc["card"]) not in used_card_ids:
                    entity_norm = sc["card"].entity.lower().strip()
                    if entity_norm not in used_entities:
                        buckets["top_stories"].append(sc["card"])
                        used_entities.add(entity_norm)
                        used_card_ids.add(id(sc["card"]))
                        eu_slot_filled = True
                        break
        
        if self.require_china_in_top5 and cards_by_region.get("CHINA"):
            for sc in cards_by_region["CHINA"]:
                if id(sc["card"]) not in used_card_ids:
                    entity_norm = sc["card"].entity.lower().strip()
                    if entity_norm not in used_entities:
                        buckets["top_stories"].append(sc["card"])
                        used_entities.add(entity_norm)
                        used_card_ids.add(id(sc["card"]))
                        china_slot_filled = True
                        break
        
        # Check for US macro story
        if self.require_us_in_top5:
            for sc in cards_by_region.get("US", []):
                if id(sc["card"]) not in used_card_ids and self._is_macro(sc["card"]):
                    entity_norm = sc["card"].entity.lower().strip()
                    if entity_norm not in used_entities:
                        buckets["top_stories"].append(sc["card"])
                        used_entities.add(entity_norm)
                        used_card_ids.add(id(sc["card"]))
                        us_macro_slot_filled = True
                        break
        
        # Second pass: Fill remaining Top 5 slots by score
        for sc in scored_cards:
            if len(buckets["top_stories"]) >= 5:
                break
                
            card = sc["card"]
            if id(card) in used_card_ids:
                continue
            
            # BUGFIX: Exclude watchlist items from Top 5 - they have their own section
            card_tickers = [t.upper() for t in card.tickers]
            if any(t in self.watchlist for t in card_tickers):
                continue
            
            entity_norm = card.entity.lower().strip()
            if entity_norm in used_entities:
                continue
            
            # Add to top stories
            buckets["top_stories"].append(card)
            used_entities.add(entity_norm)
            used_card_ids.add(id(card))
        
        # Phase 3: Assign remaining cards to Macro or Company/Markets
        for sc in scored_cards:
            card = sc["card"]
            if id(card) in used_card_ids:
                continue
            
            if self._is_macro(card):
                buckets["macro_policy"].append(card)
            else:
                buckets["company_markets"].append(card)

        # Compute aggregate sentiment for the daily brief
        sentiment_summary = None
        if sentiment_analyzer:
            sentiment_summary = sentiment_analyzer.compute_market_mood(cards)
            logger.info(f"Market sentiment: {sentiment_summary['signal']} (score: {sentiment_summary['overall_score']:.2f})")

        # Log coverage metrics
        top5_regions = [card_regions.get(id(c), "OTHER") for c in buckets["top_stories"]]
        logger.info(f"Ranked {len(cards)} cards: "
                    f"Watchlist={len(buckets['watchlist'])}, Top={len(buckets['top_stories'])}, "
                    f"Macro={len(buckets['macro_policy'])}, Markets={len(buckets['company_markets'])}")
        logger.info(f"Top 5 regional coverage: US={top5_regions.count('US')}, EU={top5_regions.count('EU')}, China={top5_regions.count('CHINA')}")
        
        # Add metadata for composition
        buckets["sentiment_summary"] = sentiment_summary
        buckets["china_news_available"] = china_news_available
        buckets["china_note_needed"] = not china_slot_filled and self.require_china_in_top5
        buckets["top5_regions"] = {
            "us": top5_regions.count("US"),
            "eu": top5_regions.count("EU"),
            "china": top5_regions.count("CHINA"),
            "other": top5_regions.count("GLOBAL") + top5_regions.count("OTHER")
        }
        
        return buckets
    def _is_macro(self, card: FactCard) -> bool:
        """Refined heuristic to determine if a card is macro-related."""
        # 1. Broad stories with no specific tickers are often macro
        if not card.tickers:
            return True
            
        # 2. Key entities that are macro-related (central banks, gov bodies)
        macro_entities = {"fed", "ecb", "boj", "pboc", "treasury", "biden", "trump", "government"}
        entity_lower = card.entity.lower()
        if any(me in entity_lower for me in macro_entities):
            return True
            
        # 3. Keyword matching in text fields
        combined_text = (card.entity + " " + card.trend + " " + card.why_it_matters).lower()
        return any(kw in combined_text for kw in self.macro_keywords)

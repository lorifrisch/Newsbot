"""
Sentiment Analysis Module
=========================

Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) for financial news sentiment.
VADER is specifically attuned to sentiments in social media and news text.

Features:
- Free, no API costs (runs locally via NLTK)
- Outputs compound score (-1 to +1) plus pos/neg/neu breakdown
- Integrates with FactCard ranking for sentiment-weighted scores
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy load NLTK/VADER to avoid slow imports
_vader_analyzer = None


def _get_vader():
    """Lazy initialization of VADER sentiment analyzer."""
    global _vader_analyzer
    if _vader_analyzer is None:
        try:
            import nltk
            from nltk.sentiment.vader import SentimentIntensityAnalyzer
            
            # Download vader_lexicon if not present (one-time)
            try:
                nltk.data.find('sentiment/vader_lexicon.zip')
            except LookupError:
                logger.info("Downloading VADER lexicon (one-time setup)...")
                nltk.download('vader_lexicon', quiet=True)
            
            _vader_analyzer = SentimentIntensityAnalyzer()
            logger.debug("VADER sentiment analyzer initialized")
        except ImportError:
            logger.warning("NLTK not installed. Sentiment analysis disabled. Run: pip install nltk")
            return None
    return _vader_analyzer


@dataclass
class SentimentScore:
    """
    Sentiment analysis result for a piece of text.
    
    Attributes:
        compound: Normalized score from -1 (most negative) to +1 (most positive)
        positive: Proportion of positive sentiment (0-1)
        negative: Proportion of negative sentiment (0-1)
        neutral: Proportion of neutral sentiment (0-1)
        label: Human-readable label (bullish/bearish/neutral)
    """
    compound: float
    positive: float
    negative: float
    neutral: float
    label: str
    
    @property
    def market_signal(self) -> str:
        """Returns market-oriented interpretation."""
        if self.compound >= 0.3:
            return "🟢 Bullish"
        elif self.compound <= -0.3:
            return "🔴 Bearish"
        elif self.compound >= 0.1:
            return "🟡 Slightly Bullish"
        elif self.compound <= -0.1:
            return "🟠 Slightly Bearish"
        else:
            return "⚪ Neutral"


class SentimentAnalyzer:
    """
    Analyzes sentiment of financial news text using VADER.
    
    Designed for integration with the news workflow:
    - Analyze individual fact cards
    - Compute aggregate market mood
    - Provide sentiment-adjusted ranking scores
    """
    
    # Financial-specific sentiment modifiers
    # VADER's default lexicon is good but we can enhance for finance
    BULLISH_TERMS = {
        'surge', 'rally', 'soar', 'jump', 'gain', 'beat', 'exceed', 'outperform',
        'upgrade', 'bullish', 'optimistic', 'recovery', 'growth', 'expansion',
        'dovish', 'stimulus', 'easing', 'upside', 'breakout', 'strong'
    }
    
    BEARISH_TERMS = {
        'plunge', 'crash', 'tumble', 'drop', 'fall', 'miss', 'decline', 'slump',
        'downgrade', 'bearish', 'pessimistic', 'recession', 'contraction', 'cut',
        'hawkish', 'tightening', 'downside', 'breakdown', 'weak', 'warning'
    }
    
    def __init__(self):
        self.vader = _get_vader()
        self._cache: Dict[str, SentimentScore] = {}
    
    def analyze(self, text: str) -> Optional[SentimentScore]:
        """
        Analyze sentiment of a text string.
        
        Args:
            text: The text to analyze (title, trend, why_it_matters, etc.)
            
        Returns:
            SentimentScore object or None if VADER unavailable
        """
        if not self.vader or not text:
            return None
        
        # Check cache
        cache_key = text[:200]  # Truncate for cache key
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Get VADER scores
        scores = self.vader.polarity_scores(text)
        
        # Determine label
        compound = scores['compound']
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        
        result = SentimentScore(
            compound=compound,
            positive=scores['pos'],
            negative=scores['neg'],
            neutral=scores['neu'],
            label=label
        )
        
        self._cache[cache_key] = result
        return result
    
    def analyze_fact_card(self, card) -> Optional[SentimentScore]:
        """
        Analyze sentiment of a FactCard by combining its text fields.
        
        Weights: entity (1x), trend (2x), why_it_matters (1.5x), data_point (0.5x)
        """
        if not self.vader:
            return None
        
        # Combine relevant text fields with weights
        texts = []
        if hasattr(card, 'entity') and card.entity:
            texts.append(card.entity)
        if hasattr(card, 'trend') and card.trend:
            texts.extend([card.trend] * 2)  # Weight: 2x
        if hasattr(card, 'why_it_matters') and card.why_it_matters:
            texts.append(card.why_it_matters)
            texts.append(card.why_it_matters[:len(card.why_it_matters)//2])  # ~1.5x weight
        if hasattr(card, 'data_point') and card.data_point:
            texts.append(card.data_point)
        
        combined_text = " ".join(texts)
        return self.analyze(combined_text)
    
    def compute_market_mood(self, cards: List) -> Dict[str, any]:
        """
        Compute aggregate market sentiment from a list of fact cards.
        
        Returns:
            Dictionary with mood metrics for the daily brief
        """
        if not self.vader or not cards:
            return {
                "overall_score": 0.0,
                "label": "neutral",
                "signal": "⚪ Neutral",
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
                "summary": "Sentiment analysis unavailable"
            }
        
        scores = []
        bullish = 0
        bearish = 0
        neutral = 0
        
        for card in cards:
            sentiment = self.analyze_fact_card(card)
            if sentiment:
                scores.append(sentiment.compound)
                if sentiment.compound >= 0.1:
                    bullish += 1
                elif sentiment.compound <= -0.1:
                    bearish += 1
                else:
                    neutral += 1
        
        if not scores:
            return {
                "overall_score": 0.0,
                "label": "neutral",
                "signal": "⚪ Neutral",
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": len(cards),
                "summary": "No sentiment data available"
            }
        
        avg_score = sum(scores) / len(scores)
        
        # Determine overall label
        if avg_score >= 0.15:
            label = "bullish"
            signal = "🟢 Risk-On"
        elif avg_score <= -0.15:
            label = "bearish"
            signal = "🔴 Risk-Off"
        elif avg_score >= 0.05:
            label = "slightly_bullish"
            signal = "🟡 Cautiously Optimistic"
        elif avg_score <= -0.05:
            label = "slightly_bearish"
            signal = "🟠 Cautiously Pessimistic"
        else:
            label = "neutral"
            signal = "⚪ Mixed/Neutral"
        
        # Generate summary
        if bullish > bearish * 2:
            summary = f"Headlines skew bullish ({bullish}/{len(cards)} positive stories)"
        elif bearish > bullish * 2:
            summary = f"Headlines skew bearish ({bearish}/{len(cards)} negative stories)"
        elif bullish > bearish:
            summary = f"Slightly positive tone ({bullish} bullish vs {bearish} bearish)"
        elif bearish > bullish:
            summary = f"Slightly negative tone ({bearish} bearish vs {bullish} bullish)"
        else:
            summary = f"Balanced sentiment ({bullish} bullish, {bearish} bearish, {neutral} neutral)"
        
        return {
            "overall_score": round(avg_score, 3),
            "label": label,
            "signal": signal,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "summary": summary
        }
    
    def get_sentiment_boost(self, card, boost_min: float = 0.95, boost_max: float = 1.15) -> float:
        """
        Calculate a ranking boost factor based on sentiment extremity.
        
        Extreme sentiment (very bullish or bearish) = more newsworthy = higher boost.
        
        Args:
            card: FactCard to analyze
            boost_min: Minimum boost for neutral content (default 0.95, -5%)
            boost_max: Maximum boost for strong sentiment (default 1.15, +15%)
        
        Returns:
            Float multiplier (boost_min to boost_max) to apply to ranking score
        """
        sentiment = self.analyze_fact_card(card)
        if not sentiment:
            return 1.0
        
        # Absolute sentiment = newsworthiness
        # Maps |compound| (0.0-1.0) to boost range
        abs_score = abs(sentiment.compound)
        
        # Linear interpolation within configurable range
        # abs_score >= 0.6 -> max boost
        # abs_score < 0.1 -> min boost (neutral penalty)
        if abs_score >= 0.6:
            return boost_max
        elif abs_score >= 0.4:
            # Interpolate between 0.4 and 0.6
            ratio = (abs_score - 0.4) / 0.2
            mid_boost = 1.0 + (boost_max - 1.0) * 0.67  # ~1.10 with default
            return mid_boost + ratio * (boost_max - mid_boost)
        elif abs_score >= 0.2:
            # Interpolate between 0.2 and 0.4
            ratio = (abs_score - 0.2) / 0.2
            low_boost = 1.0 + (boost_max - 1.0) * 0.33  # ~1.05 with default
            mid_boost = 1.0 + (boost_max - 1.0) * 0.67
            return low_boost + ratio * (mid_boost - low_boost)
        elif abs_score >= 0.1:
            # Mild sentiment: no change
            return 1.0
        else:
            # Very neutral (less newsworthy): apply penalty
            return boost_min


# Module-level singleton for easy access
_analyzer_instance = None


def get_analyzer() -> SentimentAnalyzer:
    """Get the singleton SentimentAnalyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = SentimentAnalyzer()
    return _analyzer_instance


def analyze_text(text: str) -> Optional[SentimentScore]:
    """Convenience function to analyze text sentiment."""
    return get_analyzer().analyze(text)


def compute_market_mood(cards: List) -> Dict:
    """Convenience function to compute market mood from fact cards."""
    return get_analyzer().compute_market_mood(cards)

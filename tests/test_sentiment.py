"""
Tests for sentiment analysis module.
"""

import pytest
from unittest.mock import MagicMock


class TestSentimentAnalyzer:
    """Tests for SentimentAnalyzer class."""
    
    @pytest.fixture
    def analyzer(self):
        """Create a SentimentAnalyzer instance."""
        from src.sentiment import SentimentAnalyzer
        return SentimentAnalyzer()
    
    @pytest.mark.unit
    def test_analyze_bullish_text(self, analyzer):
        """Test sentiment analysis on bullish financial text."""
        text = "NVIDIA surges 15% on blockbuster earnings, AI boom continues"
        result = analyzer.analyze(text)
        
        assert result is not None
        assert result.compound > 0.3
        assert result.label == "positive"
        assert "Bullish" in result.market_signal
    
    @pytest.mark.unit
    def test_analyze_bearish_text(self, analyzer):
        """Test sentiment analysis on bearish financial text."""
        text = "Tesla stock plunges after disappointing delivery numbers, investors flee"
        result = analyzer.analyze(text)
        
        assert result is not None
        assert result.compound < -0.3
        assert result.label == "negative"
        assert "Bearish" in result.market_signal
    
    @pytest.mark.unit
    def test_analyze_neutral_text(self, analyzer):
        """Test sentiment analysis on neutral text."""
        text = "Company reports quarterly earnings results today"
        result = analyzer.analyze(text)
        
        assert result is not None
        assert -0.2 <= result.compound <= 0.2  # Slightly wider range for neutral
    
    @pytest.mark.unit
    def test_analyze_empty_text(self, analyzer):
        """Test handling of empty text."""
        result = analyzer.analyze("")
        assert result is None
    
    @pytest.mark.unit
    def test_analyze_none_text(self, analyzer):
        """Test handling of None text."""
        result = analyzer.analyze(None)
        assert result is None
    
    @pytest.mark.unit
    def test_analyze_fact_card(self, analyzer):
        """Test sentiment analysis on a fact card object."""
        # Create a mock fact card
        card = MagicMock()
        card.entity = "Apple"
        card.trend = "Record earnings beat expectations"
        card.why_it_matters = "Strong consumer demand drives revenue growth"
        card.data_point = "+15%"
        
        result = analyzer.analyze_fact_card(card)
        
        assert result is not None
        assert result.compound > 0  # Should be positive
    
    @pytest.mark.unit
    def test_compute_market_mood_bullish(self, analyzer):
        """Test market mood computation with mostly bullish cards."""
        cards = []
        for i in range(5):
            card = MagicMock()
            card.entity = f"Company{i}"
            card.trend = "Surges higher on strong results"
            card.why_it_matters = "Bullish outlook ahead"
            card.data_point = "+10%"
            cards.append(card)
        
        mood = analyzer.compute_market_mood(cards)
        
        assert mood["overall_score"] > 0
        assert mood["bullish_count"] > mood["bearish_count"]
        assert "Risk-On" in mood["signal"] or "Optimistic" in mood["signal"]
    
    @pytest.mark.unit
    def test_compute_market_mood_bearish(self, analyzer):
        """Test market mood computation with mostly bearish cards."""
        cards = []
        for i in range(5):
            card = MagicMock()
            card.entity = f"Company{i}"
            card.trend = "Plunges on disappointing results"
            card.why_it_matters = "Weak demand concerns investors"
            card.data_point = "-10%"
            cards.append(card)
        
        mood = analyzer.compute_market_mood(cards)
        
        assert mood["overall_score"] < 0
        assert mood["bearish_count"] > mood["bullish_count"]
        assert "Risk-Off" in mood["signal"] or "Pessimistic" in mood["signal"]
    
    @pytest.mark.unit
    def test_compute_market_mood_empty(self, analyzer):
        """Test market mood with empty cards list."""
        mood = analyzer.compute_market_mood([])
        
        assert mood["overall_score"] == 0.0
        assert mood["label"] == "neutral"
    
    @pytest.mark.unit
    def test_sentiment_boost_strong_positive(self, analyzer):
        """Test sentiment boost for strongly positive content."""
        card = MagicMock()
        card.entity = "Tech Giant"
        card.trend = "Surges to all-time high on amazing results"
        card.why_it_matters = "Exceptional growth exceeds all expectations"
        card.data_point = "+25%"
        
        boost = analyzer.get_sentiment_boost(card)
        
        # Strong sentiment should get boost >= 1.05
        assert boost >= 1.05
    
    @pytest.mark.unit
    def test_sentiment_boost_neutral(self, analyzer):
        """Test sentiment boost for neutral content."""
        card = MagicMock()
        card.entity = "Company"
        card.trend = "Reports quarterly results"
        card.why_it_matters = "Numbers in line with expectations"
        card.data_point = "0%"
        
        boost = analyzer.get_sentiment_boost(card)
        
        # Neutral sentiment may get slight penalty
        assert 0.9 <= boost <= 1.05


class TestSentimentConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    @pytest.mark.unit
    def test_analyze_text_function(self):
        """Test the analyze_text convenience function."""
        from src.sentiment import analyze_text
        
        result = analyze_text("Markets rally on positive news")
        assert result is not None
        assert hasattr(result, 'compound')
    
    @pytest.mark.unit
    def test_compute_market_mood_function(self):
        """Test the compute_market_mood convenience function."""
        from src.sentiment import compute_market_mood
        
        cards = []
        for i in range(3):
            card = MagicMock()
            card.entity = f"Entity{i}"
            card.trend = "Positive development"
            card.why_it_matters = "Good news"
            card.data_point = None
            cards.append(card)
        
        mood = compute_market_mood(cards)
        assert "overall_score" in mood
        assert "signal" in mood

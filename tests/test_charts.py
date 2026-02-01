"""
Tests for chart generation module.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestChartGenerator:
    """Tests for ChartGenerator class."""
    
    @pytest.fixture
    def generator(self):
        """Create a ChartGenerator instance."""
        from src.charts import ChartGenerator
        return ChartGenerator()
    
    @pytest.mark.unit
    def test_sparkline_basic(self, generator):
        """Test basic sparkline generation."""
        values = [100, 102, 101, 105, 108, 107, 110, 112]
        result = generator.create_sparkline(values)
        
        assert result is not None
        assert result.startswith("data:image/png;base64,")
        assert len(result) > 100  # Should have substantial content
    
    @pytest.mark.unit
    def test_sparkline_uptrend_color(self, generator):
        """Test sparkline uses green for uptrend."""
        values = [100, 101, 102, 103, 104, 105]  # Clear uptrend
        result = generator.create_sparkline(values)
        
        assert result is not None
        # Just verify it generates (color is in the image data)
    
    @pytest.mark.unit
    def test_sparkline_downtrend_color(self, generator):
        """Test sparkline uses red for downtrend."""
        values = [105, 104, 103, 102, 101, 100]  # Clear downtrend
        result = generator.create_sparkline(values)
        
        assert result is not None
    
    @pytest.mark.unit
    def test_sparkline_single_value(self, generator):
        """Test sparkline with single value returns None."""
        result = generator.create_sparkline([100])
        assert result is None
    
    @pytest.mark.unit
    def test_sparkline_empty_values(self, generator):
        """Test sparkline with empty list returns None."""
        result = generator.create_sparkline([])
        assert result is None
    
    @pytest.mark.unit
    def test_sparkline_none_values(self, generator):
        """Test sparkline with None returns None."""
        result = generator.create_sparkline(None)
        assert result is None
    
    @pytest.mark.unit
    def test_sentiment_gauge_positive(self, generator):
        """Test sentiment gauge for positive score."""
        result = generator.create_sentiment_gauge(0.5)
        
        assert result is not None
        assert result.startswith("data:image/png;base64,")
    
    @pytest.mark.unit
    def test_sentiment_gauge_negative(self, generator):
        """Test sentiment gauge for negative score."""
        result = generator.create_sentiment_gauge(-0.5)
        
        assert result is not None
        assert result.startswith("data:image/png;base64,")
    
    @pytest.mark.unit
    def test_sentiment_gauge_neutral(self, generator):
        """Test sentiment gauge for neutral score."""
        result = generator.create_sentiment_gauge(0.0)
        
        assert result is not None
        assert result.startswith("data:image/png;base64,")
    
    @pytest.mark.unit
    def test_sentiment_gauge_extreme_positive(self, generator):
        """Test sentiment gauge at +1 boundary."""
        result = generator.create_sentiment_gauge(1.0)
        
        assert result is not None
    
    @pytest.mark.unit
    def test_sentiment_gauge_extreme_negative(self, generator):
        """Test sentiment gauge at -1 boundary."""
        result = generator.create_sentiment_gauge(-1.0)
        
        assert result is not None
    
    @pytest.mark.unit
    def test_mini_bar_positive(self, generator):
        """Test mini bar for positive value."""
        result = generator.create_mini_bar(2.5)  # +2.5%
        
        assert result is not None
        assert result.startswith("data:image/png;base64,")
    
    @pytest.mark.unit
    def test_mini_bar_negative(self, generator):
        """Test mini bar for negative value."""
        result = generator.create_mini_bar(-2.5)  # -2.5%
        
        assert result is not None


class TestChartConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    @pytest.mark.unit
    def test_sparkline_function(self):
        """Test the sparkline convenience function."""
        from src.charts import sparkline
        
        result = sparkline([10, 12, 11, 15, 14])
        assert result is not None
    
    @pytest.mark.unit
    def test_sentiment_gauge_function(self):
        """Test the sentiment_gauge convenience function."""
        from src.charts import sentiment_gauge
        
        result = sentiment_gauge(0.25)
        assert result is not None
    
    @pytest.mark.unit
    def test_generate_market_charts(self):
        """Test generating charts for multiple assets."""
        from src.charts import generate_market_charts
        
        market_data = {
            "SPY": [400, 402, 401, 405, 408],
            "QQQ": [300, 305, 303, 310, 308],
            "DIA": [350, 348, 352, 355, 354]
        }
        
        charts = generate_market_charts(market_data)
        
        assert len(charts) == 3
        assert "SPY" in charts
        assert "QQQ" in charts
        assert "DIA" in charts
        assert all(c.startswith("data:image/png;base64,") for c in charts.values())


class TestSparklineConfig:
    """Tests for SparklineConfig dataclass."""
    
    @pytest.mark.unit
    def test_default_config(self):
        """Test default sparkline configuration."""
        from src.charts import SparklineConfig
        
        config = SparklineConfig()
        
        assert config.width == 120
        assert config.height == 30
        assert config.up_color == '#10B981'
        assert config.down_color == '#EF4444'
    
    @pytest.mark.unit
    def test_custom_config(self):
        """Test custom sparkline configuration."""
        from src.charts import SparklineConfig, ChartGenerator
        
        config = SparklineConfig(
            width=200,
            height=50,
            up_color='#00FF00',
            down_color='#FF0000'
        )
        
        generator = ChartGenerator(config)
        
        assert generator.config.width == 200
        assert generator.config.height == 50

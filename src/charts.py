"""
Chart Generation Module
=======================

Generates email-safe sparkline charts for market data visualization.
Uses matplotlib to create small inline PNG images.

Features:
- Free (matplotlib is open source)
- Email-compatible (inline base64 PNG or CID attachments)
- Lightweight sparklines (no axes, minimal chrome)
- Color-coded for up/down trends
"""

import logging
import io
import base64
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Lazy load matplotlib to avoid slow startup
_plt = None
_np = None


def _get_matplotlib():
    """Lazy initialization of matplotlib."""
    global _plt, _np
    if _plt is None:
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend for server use
            import matplotlib.pyplot as plt
            import numpy as np
            _plt = plt
            _np = np
            logger.debug("Matplotlib initialized for chart generation")
        except ImportError:
            logger.warning("Matplotlib not installed. Chart generation disabled. Run: pip install matplotlib")
            return None, None
    return _plt, _np


@dataclass
class SparklineConfig:
    """Configuration for sparkline appearance."""
    width: float = 120  # pixels
    height: float = 30  # pixels
    line_width: float = 1.5
    up_color: str = '#10B981'  # Green
    down_color: str = '#EF4444'  # Red
    neutral_color: str = '#6B7280'  # Gray
    fill_alpha: float = 0.15
    dpi: int = 100


class ChartGenerator:
    """
    Generates sparkline charts for email embedding.
    
    Design principles:
    - Minimal: No axes, labels, or gridlines
    - Color-coded: Green for gains, red for losses
    - Email-safe: Base64 encoded PNGs
    """
    
    def __init__(self, config: Optional[SparklineConfig] = None):
        self.config = config or SparklineConfig()
        self._plt, self._np = _get_matplotlib()
    
    def _is_available(self) -> bool:
        """Check if matplotlib is available."""
        return self._plt is not None and self._np is not None
    
    def create_sparkline(
        self,
        values: List[float],
        highlight_last: bool = True
    ) -> Optional[str]:
        """
        Create a sparkline chart from a list of values.
        
        Args:
            values: List of numeric values (e.g., prices over time)
            highlight_last: Whether to add a dot at the last value
            
        Returns:
            Base64-encoded PNG string for embedding, or None if unavailable
        """
        if not self._is_available() or not values or len(values) < 2:
            return None
        
        plt = self._plt
        np = self._np
        
        # Determine trend color
        first_val = values[0]
        last_val = values[-1]
        if last_val > first_val * 1.001:  # >0.1% gain
            color = self.config.up_color
        elif last_val < first_val * 0.999:  # >0.1% loss
            color = self.config.down_color
        else:
            color = self.config.neutral_color
        
        # Create figure with exact pixel dimensions
        fig_width = self.config.width / self.config.dpi
        fig_height = self.config.height / self.config.dpi
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=self.config.dpi)
        
        # Remove all chart chrome
        ax.axis('off')
        ax.set_xlim(-0.5, len(values) - 0.5)
        
        # Add small padding to y-axis
        y_min, y_max = min(values), max(values)
        y_range = y_max - y_min if y_max != y_min else 1
        ax.set_ylim(y_min - y_range * 0.1, y_max + y_range * 0.1)
        
        # Plot the line
        x = np.arange(len(values))
        ax.plot(x, values, color=color, linewidth=self.config.line_width, solid_capstyle='round')
        
        # Fill under the line
        ax.fill_between(x, values, y_min - y_range * 0.1, color=color, alpha=self.config.fill_alpha)
        
        # Highlight last point
        if highlight_last:
            ax.scatter([len(values) - 1], [last_val], color=color, s=15, zorder=5)
        
        # Remove margins
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
        # Save to buffer
        buf = io.BytesIO()
        fig.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        
        # Encode to base64
        buf.seek(0)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{b64}"
    
    def create_mini_bar(
        self,
        value: float,
        min_val: float = -5.0,
        max_val: float = 5.0
    ) -> Optional[str]:
        """
        Create a mini horizontal bar showing a single value (e.g., % change).
        
        Args:
            value: The value to display
            min_val: Minimum expected value (for scaling)
            max_val: Maximum expected value (for scaling)
            
        Returns:
            Base64-encoded PNG string
        """
        if not self._is_available():
            return None
        
        plt = self._plt
        
        # Determine color
        if value > 0.1:
            color = self.config.up_color
        elif value < -0.1:
            color = self.config.down_color
        else:
            color = self.config.neutral_color
        
        # Create tiny figure
        fig_width = 60 / self.config.dpi
        fig_height = 12 / self.config.dpi
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=self.config.dpi)
        ax.axis('off')
        
        # Normalize value to 0-1 range
        normalized = (value - min_val) / (max_val - min_val)
        normalized = max(0, min(1, normalized))  # Clamp to [0, 1]
        
        # Draw background bar
        ax.barh(0, 1, height=0.6, color='#E5E7EB', left=0)
        
        # Draw value bar
        ax.barh(0, normalized, height=0.6, color=color, left=0)
        
        ax.set_xlim(0, 1)
        ax.set_ylim(-0.5, 0.5)
        
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        
        buf.seek(0)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{b64}"
    
    def create_sentiment_gauge(
        self,
        score: float,
        width: int = 80,
        height: int = 20
    ) -> Optional[str]:
        """
        Create a sentiment gauge visualization.
        
        Args:
            score: Sentiment score from -1 (bearish) to +1 (bullish)
            width: Width in pixels
            height: Height in pixels
            
        Returns:
            Base64-encoded PNG string
        """
        if not self._is_available():
            return None
        
        plt = self._plt
        np = self._np
        
        fig_width = width / self.config.dpi
        fig_height = height / self.config.dpi
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=self.config.dpi)
        ax.axis('off')
        
        # Create gradient background (red -> yellow -> green)
        gradient = np.linspace(0, 1, 100).reshape(1, -1)
        gradient = np.vstack([gradient, gradient])
        
        # Custom colormap: red -> yellow -> green
        from matplotlib.colors import LinearSegmentedColormap
        colors = ['#EF4444', '#F59E0B', '#10B981']  # Red, Yellow, Green
        cmap = LinearSegmentedColormap.from_list('sentiment', colors)
        
        ax.imshow(gradient, aspect='auto', cmap=cmap, extent=[0, 1, 0, 1])
        
        # Draw marker at score position
        marker_pos = (score + 1) / 2  # Convert -1..1 to 0..1
        marker_pos = max(0.02, min(0.98, marker_pos))
        
        ax.axvline(x=marker_pos, color='white', linewidth=2)
        ax.axvline(x=marker_pos, color='#111827', linewidth=1)
        
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', transparent=False, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        
        buf.seek(0)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{b64}"


# Convenience functions for simple use cases

_generator_instance = None


def get_generator() -> ChartGenerator:
    """Get the singleton ChartGenerator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ChartGenerator()
    return _generator_instance


def sparkline(values: List[float]) -> Optional[str]:
    """Create a sparkline from values. Returns base64 PNG or None."""
    return get_generator().create_sparkline(values)


def sentiment_gauge(score: float) -> Optional[str]:
    """Create a sentiment gauge. Returns base64 PNG or None."""
    return get_generator().create_sentiment_gauge(score)


def generate_market_charts(market_data: Dict[str, List[float]]) -> Dict[str, str]:
    """
    Generate sparklines for multiple market indices/assets.
    
    Args:
        market_data: Dict mapping asset names to price series
        
    Returns:
        Dict mapping asset names to base64 PNG strings
    """
    generator = get_generator()
    charts = {}
    
    for asset, values in market_data.items():
        chart = generator.create_sparkline(values)
        if chart:
            charts[asset] = chart
    
    return charts

"""
Market Data Fetcher - Real market data using yfinance.

Fetches current market levels for:
- Indices: S&P 500, Nasdaq, Stoxx 600
- Yields: US 10Y, German 10Y (Bund)
- FX: EUR/USD, USD/JPY
- Commodities: Brent Oil, WTI Oil
- Volatility: VIX

Falls back gracefully if data is unavailable.
"""

import logging
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from src.config import Settings

logger = logging.getLogger(__name__)

# Symbol mappings for yfinance
MARKET_SYMBOLS = {
    # Indices
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Stoxx 600": "^STOXX",  # May need fallback
    "Dow Jones": "^DJI",
    "Nikkei 225": "^N225",
    
    # Yields (using Treasury ETFs as proxies since direct yields need different approach)
    "US 10Y Yield": "^TNX",
    "US 2Y Yield": "^IRX",  # 13-week T-bill as proxy
    
    # FX
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "JPY=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CNY": "CNY=X",
    
    # Commodities
    "Brent Oil": "BZ=F",
    "WTI Oil": "CL=F",
    "Gold": "GC=F",
    "Natural Gas": "NG=F",
    
    # Volatility
    "VIX": "^VIX",
    
    # Crypto
    "Bitcoin": "BTC-USD",
}

# Priority list for daily snapshot
DEFAULT_SNAPSHOT_ASSETS = [
    "S&P 500",
    "Nasdaq",
    "Stoxx 600",
    "US 10Y Yield",
    "EUR/USD",
    "USD/JPY",
    "Brent Oil",
    "VIX",
    "Bitcoin",
]


@dataclass
class AssetQuote:
    """A single asset quote with price and change."""
    name: str
    symbol: str
    price: float
    change_pct: float
    change_abs: float
    timestamp: datetime
    is_stale: bool = False  # True if data is older than 24h
    
    @property
    def formatted_price(self) -> str:
        """Format price appropriately based on asset type."""
        if "Yield" in self.name:
            return f"{self.price:.2f}%"
        elif "USD" in self.name or "JPY" in self.name or "GBP" in self.name or "CNY" in self.name:
            return f"{self.price:.4f}"
        elif self.price > 1000:
            return f"{self.price:,.0f}"
        elif self.price > 100:
            return f"{self.price:,.1f}"
        else:
            return f"{self.price:.2f}"
    
    @property
    def formatted_change(self) -> str:
        """Format change with + or - sign."""
        sign = "+" if self.change_pct >= 0 else ""
        return f"{sign}{self.change_pct:.2f}%"
    
    @property
    def change_color(self) -> str:
        """CSS color for the change."""
        if self.change_pct > 0:
            return "#16a34a"  # Green
        elif self.change_pct < 0:
            return "#dc2626"  # Red
        return "#6b7280"  # Gray


class MarketDataFetcher:
    """
    Fetches real market data using yfinance.
    Provides graceful fallback if data is unavailable.
    """
    
    def __init__(self, settings: Settings, cache_duration_minutes: int = 15):
        """
        Initialize the market data fetcher.
        
        Args:
            settings: The application settings object
            cache_duration_minutes: How long to cache quotes (default 15 min)
        """
        self.settings = settings
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self._cache: Dict[str, Tuple[AssetQuote, datetime]] = {}
        self._yf_available = None
        
    def _check_yfinance_available(self) -> bool:
        """Check if yfinance is installed and working."""
        if self._yf_available is not None:
            return self._yf_available
        
        try:
            import yfinance as yf
            # Quick test
            test = yf.Ticker("^GSPC")
            _ = test.info
            self._yf_available = True
            logger.info("yfinance available and working")
        except ImportError:
            logger.warning("yfinance not installed. Run: pip install yfinance")
            self._yf_available = False
        except Exception as e:
            logger.warning(f"yfinance test failed: {e}")
            self._yf_available = False
        
        return self._yf_available
    
    def fetch_quote(self, asset_name: str) -> Optional[AssetQuote]:
        """
        Fetch a single asset quote.
        
        Args:
            asset_name: Human-readable asset name (e.g., "S&P 500")
            
        Returns:
            AssetQuote if successful, None otherwise
        """
        if not self._check_yfinance_available():
            return None
        
        symbol = MARKET_SYMBOLS.get(asset_name)
        if not symbol:
            logger.warning(f"Unknown asset: {asset_name}")
            return None
        
        # Check cache
        cache_key = asset_name
        if cache_key in self._cache:
            cached_quote, cached_time = self._cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_quote
        
        try:
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            
            # Get current price info
            info = ticker.info
            
            # Try to get price from different fields (yfinance is inconsistent)
            price = (
                info.get('regularMarketPrice') or
                info.get('currentPrice') or
                info.get('previousClose') or
                info.get('ask') or
                info.get('bid')
            )
            
            if price is None:
                # Fallback: use history
                hist = ticker.history(period="2d")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else price
                else:
                    logger.warning(f"No price data for {asset_name}")
                    return None
            else:
                prev_price = info.get('previousClose') or info.get('regularMarketPreviousClose') or price
            
            # Calculate change
            change_abs = price - prev_price
            change_pct = (change_abs / prev_price * 100) if prev_price != 0 else 0
            
            # Check if data is stale
            market_time = info.get('regularMarketTime')
            if market_time:
                data_time = datetime.fromtimestamp(market_time)
                is_stale = (datetime.now() - data_time) > timedelta(hours=24)
            else:
                is_stale = False
                data_time = datetime.now()
            
            quote = AssetQuote(
                name=asset_name,
                symbol=symbol,
                price=price,
                change_pct=change_pct,
                change_abs=change_abs,
                timestamp=data_time,
                is_stale=is_stale
            )
            
            # Cache the result
            self._cache[cache_key] = (quote, datetime.now())
            
            return quote
            
        except Exception as e:
            logger.warning(f"Failed to fetch {asset_name}: {e}")
            return None
    
    def fetch_snapshot(self, assets: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch market snapshot for multiple assets.
        
        Args:
            assets: List of asset names to fetch (default: settings or DEFAULT_SNAPSHOT_ASSETS)
            
        Returns:
            Dict with:
                - 'success': bool
                - 'quotes': List of AssetQuote dicts
                - 'timestamp': ISO timestamp
                - 'message': Status message
        """
        if assets is None:
            # Use settings if available, else fallback to default list
            assets = self.settings.market_data.snapshot_assets or DEFAULT_SNAPSHOT_ASSETS
        
        if not self._check_yfinance_available():
            return {
                'success': False,
                'quotes': [],
                'timestamp': datetime.now().isoformat(),
                'message': 'Market data unavailable (yfinance not installed)'
            }
        
        quotes = []
        failed = []
        
        for asset_name in assets:
            quote = self.fetch_quote(asset_name)
            if quote:
                quotes.append({
                    'name': quote.name,
                    'price': quote.formatted_price,
                    'change': quote.formatted_change,
                    'change_pct': quote.change_pct,
                    'color': quote.change_color,
                    'is_stale': quote.is_stale
                })
            else:
                failed.append(asset_name)
        
        success = len(quotes) >= 3  # At least 3 assets needed for a useful snapshot
        
        if failed:
            logger.warning(f"Failed to fetch: {', '.join(failed)}")
        
        return {
            'success': success,
            'quotes': quotes,
            'timestamp': datetime.now().isoformat(),
            'message': f"Fetched {len(quotes)}/{len(assets)} assets" if success else "Insufficient market data"
        }
    
    def format_snapshot_markdown(self, assets: Optional[List[str]] = None) -> str:
        """
        Generate a markdown table for the market snapshot.
        
        Returns:
            Markdown table string, or unavailable message
        """
        result = self.fetch_snapshot(assets)
        
        if not result['success'] or not result['quotes']:
            return (
                "**Market Snapshot**\n\n"
                "_Market data unavailable. No pricing feed integrated yet._"
            )
        
        # Build markdown table
        lines = [
            "| Asset | Level | Change |",
            "|-------|-------|--------|",
        ]
        
        for q in result['quotes']:
            stale_marker = " *" if q['is_stale'] else ""
            lines.append(f"| {q['name']}{stale_marker} | {q['price']} | {q['change']} |")
        
        if any(q['is_stale'] for q in result['quotes']):
            lines.append("")
            lines.append("_* Delayed data_")
        
        return "\n".join(lines)
    
    def format_snapshot_html(self, assets: Optional[List[str]] = None) -> str:
        """
        Generate styled HTML for the market snapshot.
        
        Returns:
            HTML string with inline styles for email
        """
        result = self.fetch_snapshot(assets)
        
        if not result['success'] or not result['quotes']:
            return (
                '<div style="padding: 16px; background: #f3f4f6; border-radius: 8px; '
                'text-align: center; color: #6b7280; font-style: italic;">'
                'Market snapshot unavailable (no pricing feed integrated yet).'
                '</div>'
            )
        
        # Build HTML table
        rows = []
        for q in result['quotes']:
            change_style = f'color: {q["color"]}; font-weight: 600;'
            stale_marker = '<span style="color: #9ca3af;">*</span>' if q['is_stale'] else ""
            
            rows.append(f'''
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; font-weight: 500;">
                        {q['name']}{stale_marker}
                    </td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; text-align: right;">
                        {q['price']}
                    </td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; text-align: right; {change_style}">
                        {q['change']}
                    </td>
                </tr>
            ''')
        
        table_html = f'''
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
            <thead>
                <tr style="background: #f8fafc;">
                    <th style="padding: 10px 12px; text-align: left; font-weight: 600; color: #475569; border-bottom: 2px solid #e5e7eb;">
                        Asset
                    </th>
                    <th style="padding: 10px 12px; text-align: right; font-weight: 600; color: #475569; border-bottom: 2px solid #e5e7eb;">
                        Level
                    </th>
                    <th style="padding: 10px 12px; text-align: right; font-weight: 600; color: #475569; border-bottom: 2px solid #e5e7eb;">
                        Change
                    </th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        '''
        
        if any(q['is_stale'] for q in result['quotes']):
            table_html += '<div style="font-size: 11px; color: #9ca3af; margin-top: 8px;">* Delayed data</div>'
        
        return table_html


# Singleton instance for convenience
_fetcher_instance: Optional[MarketDataFetcher] = None


def get_market_data_fetcher() -> MarketDataFetcher:
    """Get or create the singleton market data fetcher."""
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = MarketDataFetcher()
    return _fetcher_instance


def fetch_market_snapshot_html() -> str:
    """Convenience function to get HTML market snapshot."""
    return get_market_data_fetcher().format_snapshot_html()


def fetch_market_snapshot_markdown() -> str:
    """Convenience function to get markdown market snapshot."""
    return get_market_data_fetcher().format_snapshot_markdown()

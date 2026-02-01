import logging
import json
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
from src.config import Settings
from src.openai_client import OpenAIClient
from src.extract import FactCard

logger = logging.getLogger(__name__)


def _group_watchlist_by_ticker(cards: List[FactCard], watchlist: Set[str], max_per_ticker: int = 2) -> Dict[str, List[FactCard]]:
    """
    Group watchlist cards by ticker and select top N per ticker.
    Returns dict mapping ticker -> list of cards (max 2 each).
    """
    ticker_cards: Dict[str, List[FactCard]] = defaultdict(list)
    
    for card in cards:
        card_tickers = [t.upper() for t in card.tickers]
        for ticker in card_tickers:
            if ticker in watchlist:
                ticker_cards[ticker].append(card)
    
    # Sort each ticker's cards by confidence (highest first) and take top N
    result = {}
    for ticker, ticker_card_list in ticker_cards.items():
        sorted_cards = sorted(ticker_card_list, key=lambda c: c.confidence, reverse=True)
        result[ticker] = sorted_cards[:max_per_ticker]
    
    return result


def _format_watchlist_context_by_ticker(
    grouped_cards: Dict[str, List[FactCard]], 
    watchlist: Set[str]
) -> str:
    """
    Format watchlist context organized by ticker. 
    Shows all 10 watchlist tickers, even if no news.
    """
    lines = []
    
    # Sort tickers alphabetically for consistent ordering
    all_tickers = sorted(watchlist)
    
    for ticker in all_tickers:
        cards = grouped_cards.get(ticker, [])
        lines.append(f"\n**{ticker}:**")
        
        if not cards:
            lines.append("  - No major updates today")
        else:
            for card in cards:
                source_links = ", ".join([f"[{s}]({card.url})" if card.url else f"[{s}]" for s in card.sources[:2]])
                lines.append(f"  - {card.trend}")
                lines.append(f"    Insight: {card.why_it_matters}")
                if card.data_point:
                    lines.append(f"    Data: {card.data_point}")
                lines.append(f"    Sources: {source_links}")
    
    return "\n".join(lines)


class DailyBriefComposer:
    """
    Composes the daily market brief using OpenAI, focused on an analytical Bloomberg-style report.
    Integrates sentiment analysis for market mood indicator.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ai = OpenAIClient(settings)

    def compose_daily_brief(self, buckets: Dict[str, Any], market_snapshot_html: str = "") -> Dict[str, Any]:
        """
        Generates a structured daily brief using ranked fact card buckets.
        Returns a dictionary with headline, intro, and markdown sections.
        Includes sentiment summary if available.
        
        Args:
            buckets: Ranked fact card buckets from ranker
            market_snapshot_html: Pre-rendered market data HTML from yfinance
        """
        
        # Extract metadata
        sentiment_summary = buckets.pop("sentiment_summary", None)
        china_news_available = buckets.pop("china_news_available", True)
        china_note_needed = buckets.pop("china_note_needed", False)
        top5_regions = buckets.pop("top5_regions", {})
        
        # Get watchlist from settings
        watchlist = set(t.upper() for t in self.settings.watchlist_tickers)
        
        # Prepare TOP 5 context with clickable sources
        top5_cards = buckets.get("top_stories", [])
        top5_context = "\n### TOP 5 DEVELOPMENTS:\n"
        for i, card in enumerate(top5_cards, 1):
            # Format sources with URLs for clickable citations
            source_links = []
            for s in card.sources[:3]:
                if card.url:
                    source_links.append(f"[{s}]({card.url})")
                else:
                    source_links.append(f"[{s}]")
            sources_str = ", ".join(source_links)
            
            region = top5_regions.get(card.entity, "")
            region_tag = f" [{region}]" if region else ""
            
            top5_context += f"""
{i}. **{card.entity}**{region_tag}
   - What happened: {card.trend}
   - Key data: {card.data_point or 'N/A'}
   - Why it matters: {card.why_it_matters}
   - Confidence: {card.confidence}
   - Sources: {sources_str}
"""
        
        # Add China note if needed
        if china_note_needed:
            top5_context += "\n**Note:** No major China-specific developments were reported today. Monitoring continues.\n"
        
        # Prepare MACRO context with clickable sources
        macro_cards = buckets.get("macro_policy", [])
        macro_context = "\n### MACRO & POLICY:\n"
        for card in macro_cards[:6]:
            source_links = []
            for s in card.sources[:2]:
                if card.url:
                    source_links.append(f"[{s}]({card.url})")
                else:
                    source_links.append(f"[{s}]")
            sources_str = ", ".join(source_links)
            
            macro_context += f"""
- **{card.entity}**: {card.trend}
  - Insight: {card.why_it_matters}
  - Data: {card.data_point or 'N/A'}
  - Sources: {sources_str}
"""
        
        # Prepare WATCHLIST context grouped by ticker
        watchlist_cards = buckets.get("watchlist", [])
        grouped_watchlist = _group_watchlist_by_ticker(watchlist_cards, watchlist, max_per_ticker=2)
        watchlist_context = _format_watchlist_context_by_ticker(grouped_watchlist, watchlist)
        
        # Prepare COMPANY/MARKETS context
        company_cards = buckets.get("company_markets", [])
        company_context = "\n### COMPANY & MARKETS:\n"
        for card in company_cards[:8]:
            source_links = []
            for s in card.sources[:2]:
                if card.url:
                    source_links.append(f"[{s}]({card.url})")
                else:
                    source_links.append(f"[{s}]")
            sources_str = ", ".join(source_links)
            
            company_context += f"""
- **{card.entity}**: {card.trend}
  - Data: {card.data_point or 'N/A'}
  - Sources: {sources_str}
"""

        # Add sentiment context to prompt
        sentiment_context = ""
        if sentiment_summary:
            sentiment_context = f"""
        
MARKET SENTIMENT ANALYSIS:
- Overall Signal: {sentiment_summary.get('signal', 'N/A')}
- Sentiment Score: {sentiment_summary.get('overall_score', 0):.2f} (scale: -1 bearish to +1 bullish)
- Breakdown: {sentiment_summary.get('bullish_count', 0)} bullish, {sentiment_summary.get('bearish_count', 0)} bearish, {sentiment_summary.get('neutral_count', 0)} neutral stories
- Summary: {sentiment_summary.get('summary', 'N/A')}
"""

        prompt = f"""
You are a senior financial editor at Bloomberg. Synthesize the following markets data into a premium daily brief.

DATA FOR TODAY:
{top5_context}
{macro_context}

WATCHLIST (User's 10 tracked tickers - MUST include ALL of them):
{watchlist_context}
{company_context}
{sentiment_context}

WRITING REQUIREMENTS:
1. **STRUCTURE FOR EACH STORY**: Use this format:
   - **What happened**: The factual news (1-2 sentences)
   - **Why it matters**: Analysis of investor implications (1-2 sentences)
   - Include key numbers (%, $, basis points) when available

2. **CITATIONS**: 
   - EVERY bullet point MUST have a clickable source link in Markdown format: [Source Name](URL)
   - Use the exact source links provided in the data above
   - Format: "...the Fed signaled patience [Reuters](https://reuters.com/...)."

3. **STYLE**: 
   - Strictly analytical, professional, and dense
   - No boilerplate intro like "Welcome to today's news"
   - Bloomberg/FT tone - assume reader is a professional investor

4. **DEPTH**: 
   - Top 5 stories: 3-4 sentences each with analysis
   - Macro section: 2-3 meaty paragraphs connecting themes
   - Watchlist: Cover ALL 10 tickers, even if just "No major updates"

5. **SENTIMENT**: Reference the sentiment analysis in your intro if meaningful

OUTPUT FORMAT - Return ONLY a JSON object with these fields:
- 'headline': Specific, punchy (e.g., "Yields Pivot on Unexpected ISM Cool, Tech Gains")
- 'preheader': 1-sentence teaser for email preview
- 'intro': 3-sentence executive summary. Set the analytical tone.
- 'top5_md': Markdown with exactly 5 stories. Use the "What happened / Why it matters" structure. Include [Source](URL) links.
- 'macro_md': 2-3 Markdown paragraphs on central banks, rates, and macro themes. Include source links.
- 'watchlist_md': Markdown list covering ALL 10 watchlist tickers. Group by ticker symbol. Include source links where available.
- 'what_to_watch_md': 2-3 bullets on what to monitor tomorrow/this week based on today's news.

CRITICAL RULES:
- Never hallucinate numbers - use "not disclosed" or "---" if missing
- ALL 10 watchlist tickers MUST appear in watchlist_md
- Include clickable [Source](URL) citations in every section
- If no China news today, include the China note in the macro section
"""

        logger.info("Requesting synthesis from OpenAI...")
        
        try:
            response = self.ai.responses_create(
                model_type="write",
                messages=[
                    {"role": "system", "content": "You are a senior financial macro editor. Output valid JSON only. Always include Markdown links for sources."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_output_tokens=3000,  # Increased for better depth
                purpose="daily_composition"
            )
            
            content = response.choices[0].message.content
            report = json.loads(content)
            
            # Post-process: ensure markdown fields are strings
            md_fields = ['top5_md', 'macro_md', 'watchlist_md', 'what_to_watch_md']
            for field in md_fields:
                if field in report and isinstance(report[field], list):
                    report[field] = "\n".join([str(item) for item in report[field]])
            
            # Use real market data for snapshot instead of AI-generated
            if market_snapshot_html:
                report["snapshot_md"] = ""  # Clear - we'll use HTML directly
                report["snapshot_html"] = market_snapshot_html
            else:
                report["snapshot_md"] = "| Asset | Status |\n|---|---|\n| Market Data | Unavailable |"
                report["snapshot_html"] = ""
            
            # Add metadata for downstream processing
            report["china_note_needed"] = china_note_needed
            report["watchlist_tickers_expected"] = list(watchlist)
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to compose daily brief: {e}")
            return {
                "headline": "Morning Markets Update",
                "preheader": "Macro shifts and equity movers.",
                "intro": "The markets are processing recent developments across key regions.",
                "top5_md": "* Data processing error. Please refer to underlying sources.",
                "macro_md": "Macro analysis is currently unavailable.",
                "watchlist_md": "Watchlist updates unavailable.",
                "what_to_watch_md": "* Check back for updates.",
                "snapshot_md": "| Asset | Status |\n|---|---|\n| Market Data | Unavailable |",
                "snapshot_html": market_snapshot_html or ""
            }

    def compose_weekly_recap(self, fact_cards: List[FactCard]) -> Dict[str, Any]:
        """
        Generates a weekly market recap using fact cards stored in the database.
        Returns a dictionary with headline, intro, and markdown sections optimized for weekly synthesis.
        """
        
        # Prepare weekly context from fact cards
        context_str = ""
        for card in fact_cards:
            context_str += (
                f"- Entity: {card.entity}\n"
                f"  Trend: {card.trend}\n"
                f"  Insight: {card.why_it_matters}\n"
                f"  Data: {card.data_point or 'N/A'}\n"
                f"  Confidence: {card.confidence}\n"
                f"  Date: {card.timestamp if hasattr(card, 'timestamp') else 'This week'}\n"
                f"  Sources: {', '.join(card.sources)}\n\n"
            )

        prompt = f"""
        You are a senior financial editor at Bloomberg preparing the Sunday Weekly Markets Recap.
        
        DATA FROM THE PAST 7 DAYS:
        {context_str}
        
        CORE REQUIREMENTS:
        1. STYLE: Authoritative, thematic, "big picture" analysis. Connect dots across the week.
        2. SOURCES: Reference sources in brackets [Source Name] where appropriate.
        3. LENGTH: Aim for 10-15 minute read depth (~2000-3000 words equivalent). Token limit: 3500.
        4. STRUCTURE: Output ONLY a JSON object with these fields:
           - 'headline': Capture the week's dominant theme (e.g., "Markets Digest Fed Hawkishness Amid Tech Rotation").
           - 'preheader': 1-sentence hook for the week.
           - 'intro': 3-4 sentence executive summary of the week's narrative.
           - 'top5_md': Markdown list of the **Top 10 Developments** of the week. Each bullet should synthesize related stories.
           - 'macro_md': 2-4 detailed Markdown paragraphs on **Theme of the Week** and **Biggest Market Drivers** (rates, policy, macro).
           - 'watchlist_md': Markdown list for **Watchlist Weekly Wrap** - key corporate/sector moves.
           - 'snapshot_md': A Markdown section titled **Next Week to Watch** with 3-5 bullets on upcoming events, data releases, or themes.
        
        ANALYSIS DEPTH:
        - Identify recurring themes (e.g., "dovish pivot continued all week").
        - Highlight turning points or surprises.
        - Connect micro (earnings, M&A) to macro (Fed, geopolitics).
        - Use "not disclosed" or "---" for missing data.
        
        Output valid JSON only.
        """

        logger.info("Requesting weekly recap synthesis from OpenAI...")
        
        try:
            response = self.ai.responses_create(
                model_type="write",
                messages=[
                    {"role": "system", "content": "You are a senior financial macro editor. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_output_tokens=4000,  # Weekly recap can be longer
                purpose="weekly_composition"  # For budget tracking
            )
            
            content = response.choices[0].message.content
            report = json.loads(content)
            
            # Post-process: ensure markdown fields are strings (OpenAI sometimes returns lists)
            md_fields = ['top5_md', 'macro_md', 'watchlist_md', 'snapshot_md']
            for field in md_fields:
                if field in report and isinstance(report[field], list):
                    report[field] = "\n".join([str(item) for item in report[field]])
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to compose weekly recap: {e}")
            return {
                "headline": "Weekly Markets Recap",
                "preheader": "A review of the week's key developments.",
                "intro": "Markets processed several key themes this week across equities, rates, and policy.",
                "top5_md": "* Data processing error. Please refer to underlying sources.",
                "macro_md": "Weekly macro analysis is currently unavailable.",
                "watchlist_md": "Watchlist updates unavailable.",
                "snapshot_md": "**Next Week to Watch**\n* Check back for upcoming events."
            }

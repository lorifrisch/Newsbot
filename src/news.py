import logging
from typing import List, Dict, Any
from src.config import Settings
from src.retrieval import MarketNewsItem
from src.clustering import StoryCluster
from src.openai_client import OpenAIClient
from src.extract import FactCard

logger = logging.getLogger(__name__)

class ContentComposer:
    """
    Handles news extraction and composition using our OpenAI wrapper.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ai = OpenAIClient(settings)

    def compose_ranked_brief(self, buckets: Dict[str, List[FactCard]]) -> Dict[str, Any]:
        """
        Uses OpenAI to process ranked buckets into the final HTML brief structure.
        """
        def format_section(title: str, cards: List[FactCard]) -> str:
            if not cards:
                return f"{title}: No significant updates.\n"
            data = f"{title}:\n"
            for c in cards:
                tickers = f" ({', '.join(c.tickers)})" if c.tickers else ""
                data += f"- {c.entity}{tickers}: {c.trend}. Impact: {c.why_it_matters}. Data: {c.data_point or 'N/A'}. Sources: {', '.join(c.sources)}\n"
            return data

        full_context = (
            format_section("TOP STORIES", buckets.get("top_stories", [])) +
            format_section("MACRO & POLICY", buckets.get("macro_policy", [])) +
            format_section("WATCHLIST UPDATES", buckets.get("watchlist", [])) +
            format_section("OTHER MARKET NEWS", buckets.get("company_markets", []))
        )

        logger.info("Synthesizing final brief from ranked fact cards...")

        prompt = f"""
        Draft a high-end financial daily brief based on these extracted fact cards.
        
        Fact Data:
        {full_context}
        
        Instructions:
        1. 'news_headline': A 40-60 character punchy headline.
        2. 'intro_paragraph': A 2-sentence executive summary that sets the tone for the day.
        3. 'top5_html': Format TOP STORIES as a professional HTML <ul> list. Use <li><strong>Entity:</strong> Sharp summary highlighting trend and impact</li>. Keep it to 5 items max as per input.
        4. 'macro_html': Synthesize MACRO & POLICY into 1-2 sharp, analytical HTML paragraphs. Focus on the 'why' and forward-looking implications.
        5. 'watchlist_html': Provide a clean HTML list or table for WATCHLIST UPDATES. Mention specific tickers.
        6. 'snapshot_html': Create a 3-column HTML table (Index/Asset, Price/Level, Change) for major indices based on standard market data (S&P 500, Nasdaq 100, 10Y Treasury, Gold). If specific values aren't in fact cards, use placeholders like '---' or typical market levels if you have them, but prefer data from the cards if available.
        7. 'preheader': 1-sentence teaser for email apps.
        
        Return valid JSON only. Style should be concise, professional, and slightly analytical (Bloomberg/Reuters style).
        """

        try:
            response = self.ai.responses_create(
                model_type="write",
                messages=[
                    {"role": "system", "content": "You are a senior financial editor at a top investment bank. You output only valid JSON with HTML values."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_output_tokens=2500
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Failed to compose ranked brief: {e}")
            raise

    def extract_and_format(self, clusters: List[StoryCluster]) -> Dict[str, Any]:
        """
        Uses OpenAI to process story clusters into structured context for the email template.
        """
        # Convert clusters to a readable string format for the LLM
        combined_raw = ""
        for cluster in clusters:
            p = cluster.primary_item
            sources = [p.source] + [s.source for s in cluster.supporting_items]
            combined_raw += f"Title: {p.title}\n"
            combined_raw += f"Sources: {', '.join(sources)}\n"
            combined_raw += f"Region: {p.region}\n"
            combined_raw += f"Snippet: {p.snippet}\n"
            combined_raw += f"URL: {p.url}\n\n"
        
        logger.info(f"Composing structured news brief from {len(clusters)} clusters using OpenAI...")
        
        prompt = f"""
        Process the following raw market news into a structured daily brief for an investor.
        
        Raw News:
        {combined_raw}
        
        Instructions:
        1. Identify the 'Top 5 must-know' events. Format each as a bullet point with a <strong>Ticker/Topic:</strong> followed by a 1-2 sentence summary.
        2. Summarize 'Macro & Policy' updates into a concise paragraph.
        3. Create a 'Markets Snapshot' table in HTML (3 columns: Index/Asset, Value, Change).
        4. Provide a 'Watchlist' update for the tickers mentioned in the raw data.
        
        Return the result as a JSON object with the following keys:
        - news_headline: A catchy headline for today's brief.
        - intro_paragraph: A 2-sentence market opening summary.
        - top5_html: The HTML string for the Top 5 list.
        - macro_html: The HTML string for the Macro section.
        - snapshot_html: The HTML string for the snapshot table.
        - watchlist_html: The HTML string for the watchlist section.
        - preheader: A short preview text.
        - fact_cards: A list of objects, each with:
            - entity: (e.g., 'Federal Reserve', 'NVIDIA')
            - trend: (e.g., 'Increasing rates', 'Strong earnings')
            - data_point: (e.g., '5.25%', '$1.2B revenue')
            - url: (The source URL from the raw news)
        """

        try:
            response = self.ai.responses_create(
                model_type="write",
                messages=[
                    {"role": "system", "content": "You are a financial news editor. You must output valid JSON. Use valid HTML tags inside the HTML strings (e.g. <ul>, <li>, <strong>, <p>)."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_output_tokens=2000
            )
            import json
            content = json.loads(response.choices[0].message.content)
            
            # Ensure fact_cards exists and is a list
            if "fact_cards" not in content or not isinstance(content["fact_cards"], list):
                content["fact_cards"] = []
                
            return content
        except Exception as e:
            logger.error(f"Failed to compose news brief: {e}")
            raise

    def compose_weekly_recap(self, fact_cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Uses OpenAI to synthesize a week's worth of fact cards into a recap.
        """
        if not fact_cards:
            return {}

        combined_raw = ""
        for card in fact_cards:
            combined_raw += f"Entity: {card.get('entity')}\nTrend: {card.get('trend')}\nData: {card.get('data_point')}\nSource: {card.get('url')}\n\n"

        logger.info(f"Synthesizing weekly recap from {len(fact_cards)} cards...")

        prompt = f"""
        Analyze the following financial fact cards from the past week and create a comprehensive weekly recap for an investor.
        
        Fact Cards:
        {combined_raw}
        
        Instructions:
        1. Identify the 'Key Themes of the Week'.
        2. Provide a 'Winners & Losers' section in HTML format.
        3. Create a 'Look Ahead' section for the coming week.
        
        Return the result as a JSON object with the following keys:
        - news_headline: A summary headline for the week.
        - intro_paragraph: A 3-sentence weekly summary.
        - top5_html: The HTML string for the 'Themes of the Week'.
        - macro_html: The HTML string for the 'Synthesis' section.
        - snapshot_html: The HTML string for 'Weekly Market Performance' table.
        - watchlist_html: The HTML string for 'Watchlist Updates'.
        - preheader: A short preview text.
        """

        try:
            response = self.ai.responses_create(
                model_type="write",
                messages=[
                    {"role": "system", "content": "You are a financial news editor. You must output valid JSON. Use valid HTML tags inside the HTML strings."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_output_tokens=2500
            )
            import json
            content = json.loads(response.choices[0].message.content)
            return content
        except Exception as e:
            logger.error(f"Failed to compose weekly recap: {e}")
            raise


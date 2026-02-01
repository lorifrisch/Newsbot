import logging
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from src.config import Settings
from src.clustering import StoryCluster
from src.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

# Strict JSON Schema for OpenAI structured outputs
FACT_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "fact_cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "story_id": {"type": "string", "description": "Unique identifier for the story cluster"},
                    "entity": {"type": "string", "description": "Main entity (company, institution, market)"},
                    "trend": {"type": "string", "description": "What happened or is happening"},
                    "data_point": {"type": ["string", "null"], "description": "Specific number, percentage, or metric"},
                    "why_it_matters": {"type": "string", "description": "Market impact (max 200 chars)"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "0.0-1.0"},
                    "tickers": {"type": "array", "items": {"type": "string"}, "description": "Related stock tickers"},
                    "sources": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "Source names"},
                    "urls": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "Source URLs"}
                },
                "required": ["story_id", "entity", "trend", "data_point", "why_it_matters", "confidence", "tickers", "sources", "urls"],
                "additionalProperties": False
            }
        }
    },
    "required": ["fact_cards"],
    "additionalProperties": False
}

class FactCard(BaseModel):
    """
    Structured fact card with validated fields.
    """
    story_id: str = Field(..., description="Unique identifier for the story cluster")
    entity: str = Field(..., min_length=1, description="Main entity (company, institution, market)")
    trend: str = Field(..., min_length=1, description="What happened or is happening")
    data_point: Optional[str] = Field(None, description="Specific number, percentage, or metric")
    why_it_matters: str = Field(..., min_length=1, max_length=200, description="Concise explanation of impact/significance")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    tickers: List[str] = Field(default_factory=list, description="Related stock tickers if any")
    sources: List[str] = Field(default_factory=list, min_length=1, description="List of source names")
    urls: List[str] = Field(default_factory=list, min_length=1, description="List of source URLs")

    @property
    def url(self) -> Optional[str]:
        """Convenience property to get the primary URL."""
        return self.urls[0] if self.urls else None

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v

class FactCardExtractor:
    """
    Converts story clusters into structured fact cards using OpenAI with strict JSON schema.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ai = OpenAIClient(settings)
        self.max_clusters = getattr(settings.daily, 'max_clusters', 14)
        # Use strict schema if configured (default: True for better reliability)
        self.use_strict_schema = getattr(settings.models, 'use_strict_schema', True)


    def extract_fact_cards(self, clusters: List[StoryCluster]) -> List[FactCard]:
        """
        Extracts structured fact cards from story clusters.
        Implements retry logic: retries once on JSON parse or validation errors.
        """
        if not clusters:
            return []

        # Limit clusters to configured maximum
        limited_clusters = clusters[:self.max_clusters]
        logger.info(f"Extracting fact cards from {len(limited_clusters)} clusters (max: {self.max_clusters})")

        # Build the extraction prompt
        cluster_data = self._format_clusters_for_extraction(limited_clusters)
        prompt = self._build_extraction_prompt(cluster_data)

        max_retries = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Use strict JSON schema if configured
                api_kwargs = {
                    "model_type": "extract",
                    "messages": [
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    "max_output_tokens": getattr(self.settings.models, 'extraction_max_tokens', 3000),
                    "purpose": "extraction"
                }
                
                if self.use_strict_schema:
                    api_kwargs["json_schema"] = {
                        "name": "fact_cards_extraction",
                        "schema": FACT_CARD_SCHEMA
                    }
                else:
                    api_kwargs["response_format"] = {"type": "json_object"}
                
                response = self.ai.responses_create(**api_kwargs)

                raw_content = response.choices[0].message.content
                
                try:
                    result = json.loads(raw_content)
                except json.JSONDecodeError as je:
                    logger.warning(f"Attempt {attempt + 1}: JSON parse error: {je}")
                    last_error = je
                    if attempt < max_retries - 1:
                        logger.info("Retrying extraction...")
                        continue
                    raise
                
                fact_cards = []
                validation_errors = 0

                for card_data in result.get("fact_cards", []):
                    try:
                        fact_card = FactCard(**card_data)
                        fact_cards.append(fact_card)
                    except Exception as e:
                        validation_errors += 1
                        logger.warning(f"Invalid fact card skipped: {e}")

                # If too many validation errors (>50%), retry
                total_cards = len(result.get("fact_cards", []))
                if total_cards > 0 and validation_errors > total_cards * 0.5:
                    logger.warning(f"Attempt {attempt + 1}: High validation error rate ({validation_errors}/{total_cards})")
                    if attempt < max_retries - 1:
                        logger.info("Retrying extraction due to high error rate...")
                        continue

                logger.info(f"Successfully extracted {len(fact_cards)} valid fact cards (attempt {attempt + 1})")
                return fact_cards

            except json.JSONDecodeError:
                # Already logged above, will retry or exit loop
                pass
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Failed to extract fact cards: {e}")
                last_error = e
                if attempt < max_retries - 1:
                    logger.info("Retrying extraction...")
                    continue
                break
        
        logger.error(f"Extraction failed after {max_retries} attempts. Last error: {last_error}")
        return []

    def _format_clusters_for_extraction(self, clusters: List[StoryCluster]) -> List[Dict[str, Any]]:
        """
        Formats clusters into structured data for the extraction prompt.
        """
        formatted = []
        for cluster in clusters:
            sources = [cluster.primary_item.source] + [s.source for s in cluster.supporting_items]
            urls = [cluster.primary_item.url] + [s.url for s in cluster.supporting_items]
            
            formatted.append({
                "cluster_id": cluster.cluster_id,
                "primary_title": cluster.primary_item.title,
                "primary_snippet": cluster.primary_item.snippet,
                "sources": list(set(sources)),  # Remove duplicates
                "urls": list(set(urls)),  # Remove duplicates
                "supporting_count": len(cluster.supporting_items)
            })
        return formatted

    def _get_system_prompt(self) -> str:
        return """You are a financial fact extraction specialist. Extract structured fact cards from news clusters.

CRITICAL RULES:
1. DO NOT invent or estimate numbers - only use exact figures from the source material
2. Include ALL source URLs in the urls field
3. Keep why_it_matters under 200 characters and focused on market impact
4. Include relevant stock tickers when mentioned (use standard format like AAPL, TSLA)
5. Set confidence based on source quality and data specificity
6. Each fact card must have at least one source and URL
7. Only extract facts with clear market relevance

Output valid JSON only."""

    def _build_extraction_prompt(self, cluster_data: List[Dict[str, Any]]) -> str:
        clusters_text = ""
        for i, cluster in enumerate(cluster_data, 1):
            clusters_text += f"\nCluster {i} (ID: {cluster['cluster_id']}):\n"
            clusters_text += f"Title: {cluster['primary_title']}\n"
            clusters_text += f"Content: {cluster['primary_snippet']}\n"
            clusters_text += f"Sources: {', '.join(cluster['sources'])}\n"
            clusters_text += f"URLs: {', '.join(cluster['urls'])}\n"
            if cluster['supporting_count'] > 0:
                clusters_text += f"Supporting sources: {cluster['supporting_count']} additional outlets\n"

        return f"""Extract fact cards from these news clusters. Each fact card should capture a specific, actionable market insight.

{clusters_text}

Return JSON with this exact structure:
{{
  "fact_cards": [
    {{
      "story_id": "cluster_id_from_above",
      "entity": "Company/Institution/Market name",
      "trend": "What is happening (action/direction)",
      "data_point": "Specific number/percentage/metric or null if none",
      "why_it_matters": "Market impact explanation (max 200 chars)",
      "confidence": 0.85,
      "tickers": ["TICKER1", "TICKER2"],
      "sources": ["Source1", "Source2"],
      "urls": ["url1", "url2"]
    }}
  ]
}}

Extract only facts with clear market relevance. Do not create fact cards for vague or speculative content."""
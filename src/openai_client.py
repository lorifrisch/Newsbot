import time
import random
import logging
import openai
from typing import List, Dict, Optional, Any
from src.config import Settings

logger = logging.getLogger(__name__)

class OpenAIClient:
    """
    OpenAI client wrapper providing robust retry logic, 
    consistent configuration, and token budgeting.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.openai_api_key.get_secret_value()
        self.client = openai.OpenAI(api_key=self.api_key)
        self.extract_model = settings.models.extract_model
        self.write_model = settings.models.write_model
        self.fallback = settings.models.fallback_model

    def responses_create(
        self,
        messages: List[Dict[str, str]],
        model_type: str = "write", # "write" or "extract"
        max_output_tokens: int = 1000,
        temperature: float = 0.5,
        response_format: Optional[Dict[str, Any]] = None,
        json_schema: Optional[Dict[str, Any]] = None,  # NEW: Strict JSON schema
        max_retries: int = 3,
        initial_backoff: float = 2.0,
        purpose: Optional[str] = None  # For logging
    ) -> Dict[str, Any]:
        """
        Creates a chat completion with retry logic and token capping.
        
        Args:
            json_schema: If provided, enables strict JSON schema mode (OpenAI structured outputs).
                         Format: {"name": "schema_name", "schema": {...}}
        
        Returns the parsed response object.
        """
        model = self.write_model if model_type == "write" else self.extract_model
        retries = 0
        backoff = initial_backoff

        while retries <= max_retries:
            try:
                # Use current try's model
                active_model = model if retries == 0 else self.fallback
                
                logger.info(f"OpenAI Request [{model_type}]: {active_model} (cap={max_output_tokens})")
                
                # Build response_format with optional strict schema
                final_response_format = response_format
                if json_schema:
                    # Strict JSON schema mode (OpenAI structured outputs)
                    final_response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": json_schema.get("name", "response"),
                            "strict": True,
                            "schema": json_schema.get("schema", json_schema)
                        }
                    }
                    logger.debug(f"Using strict JSON schema: {json_schema.get('name', 'response')}")
                
                response = self.client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    max_completion_tokens=max_output_tokens,
                    temperature=temperature,
                    response_format=final_response_format
                )
                
                # Log usage for budget tracking
                usage = response.usage
                logger.info(
                    f"OpenAI Usage: {usage.total_tokens} tokens "
                    f"(Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens})"
                )
                
                return response

            except (openai.RateLimitError, openai.InternalServerError, openai.APIStatusError) as e:
                # Use getattr safely for status_code
                try:
                    status_code = getattr(e, 'status_code', None)
                    if status_code is None and isinstance(e, openai.APIStatusError):
                        status_code = e.status_code
                except:
                    status_code = 'Unknown'
                
                # Check if it's a 429 or 5xx before retrying
                is_retryable = (status_code == 429) or (isinstance(status_code, int) and status_code >= 500)
                
                # RateLimitError is always retryable even if status_code check fails
                if isinstance(e, openai.RateLimitError):
                    is_retryable = True
                    status_code = 429
                
                if not is_retryable or retries == max_retries:
                    logger.error(f"OpenAI API error {status_code}: {e}")
                    raise

                # Check for Retry-After header (best practice)
                retry_after = None
                if hasattr(e, 'response') and e.response and hasattr(e.response, 'headers'):
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            retry_after = float(retry_after)
                            logger.info(f"Using Retry-After header: {retry_after}s")
                        except (ValueError, TypeError):
                            retry_after = None
                
                # Calculate backoff with jitter (±25%)
                if retry_after:
                    delay = retry_after
                else:
                    jitter = random.uniform(0.75, 1.25)
                    delay = backoff * jitter

                logger.warning(
                    f"OpenAI API error {status_code}. "
                    f"Retrying with fallback in {delay:.1f}s... ({retries + 1}/{max_retries})"
                )
                time.sleep(delay)
                retries += 1
                backoff *= 2  # Exponential backoff

            except Exception as e:
                logger.error(f"Unexpected error in OpenAIClient: {e}")
                raise

        raise Exception("Max retries reached for OpenAI")

import time
import random
import logging
import openai
from typing import List, Dict, Optional, Any
from src.config import Settings

logger = logging.getLogger(__name__)

class PerplexityClient:
    """
    Specialized client for Perplexity AI providing robust retry logic for 
    reliable news retrieval. Features exponential backoff for 429 and 5xx.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.perplexity_api_key.get_secret_value()
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.perplexity.ai"
        )
        self.default_model = settings.models.retrieval

    def chat(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
        temperature: float = 0.2,
        timeout: float = 60.0
    ) -> str:
        """
        Sends a chat completion request to Perplexity with exponential backoff on 429 and 5xx.
        """
        model = model or self.default_model
        retries = 0
        backoff = initial_backoff

        while retries <= max_retries:
            try:
                # Use the client to create a completion
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=timeout
                )
                return response.choices[0].message.content

            except (openai.RateLimitError, openai.InternalServerError, openai.APIStatusError) as e:
                # Retry on 429 and 5xx errors
                status_code = getattr(e, 'status_code', 'Unknown')
                
                # Check if it's a 429 or 5xx before retrying
                is_retryable = (status_code == 429) or (isinstance(status_code, int) and status_code >= 500)
                
                if not is_retryable or retries == max_retries:
                    logger.error(f"Perplexity API error {status_code}: {e}")
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
                    f"Perplexity API error {status_code}. "
                    f"Retrying in {delay:.1f}s... ({retries + 1}/{max_retries})"
                )
                time.sleep(delay)
                retries += 1
                backoff *= 2  # Exponential backoff

            except openai.APITimeoutError as e:
                if retries == max_retries:
                    logger.error(f"Perplexity Timeout error after {max_retries} retries: {e}")
                    raise
                
                # Apply jitter to timeout backoff too
                jitter = random.uniform(0.75, 1.25)
                delay = backoff * jitter
                
                logger.warning(f"Perplexity Timeout error. Retrying in {delay:.1f}s... ({retries + 1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                backoff *= 2

            except Exception as e:
                logger.error(f"Unexpected error in PerplexityClient: {e}")
                raise

        return "" # Should not reach here

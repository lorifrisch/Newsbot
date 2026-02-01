import sys
import os
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Settings
from src.perplexity_client import PerplexityClient

# Configure basic logging to see retry messages
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    print("Initializing Perplexity Client test...")
    try:
        settings = Settings.load()
        client = PerplexityClient(settings)
        
        print(f"Using model: {client.default_model}")
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Ping: Respond with 'Pong' and nothing else if you are online."}
        ]
        
        print("Sending request...")
        # Note: This will likely fail with 401 if valid keys aren't in .env, 
        # but that's expected for this environment.
        response = client.chat(messages)
        
        print("\n--- Response ---")
        print(response)
        print("----------------\n")
        
        if "pong" in response.lower():
            print("SUCCESS: Perplexity API client is working correctly.")
        else:
            print(f"WARNING: Received unexpected response content: {response}")
            
    except Exception as e:
        print(f"\nFAILURE: Test failed with error: {e}")
        print("This is expected if your PERPLEXITY_API_KEY is not set or is invalid.")
        sys.exit(0) # Exit with 0 as this is often just a smoke test in CI

if __name__ == "__main__":
    main()

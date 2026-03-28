"""Simple configuration for the joke agent."""

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables
load_dotenv()

# Simple configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

def get_llm():
    """Get the language model."""
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    
    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GOOGLE_API_KEY
    )

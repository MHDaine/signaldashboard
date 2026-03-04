"""Research providers for Signal Collection."""

from .base import BaseProvider, RawSignal, ProviderResult
from .perplexity import PerplexityProvider
from .gemini import GeminiProvider
from .websearch import WebSearchProvider
from .mcp import MCPProvider
from .linkedin import LinkedInProvider
from .reddit import RedditProvider
from .twitter import TwitterProvider

__all__ = [
    "BaseProvider",
    "RawSignal",
    "ProviderResult",
    "PerplexityProvider",
    "GeminiProvider",
    "WebSearchProvider",
    "MCPProvider",
    "LinkedInProvider",
    "RedditProvider",
    "TwitterProvider",
]


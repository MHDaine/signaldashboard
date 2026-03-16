"""Configuration management for Signal Collection API."""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys for Research Providers
    perplexity_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_key: Optional[str] = None  # Alternative name
    openai_api_key: Optional[str] = None
    google_search_api_key: Optional[str] = None
    google_search_engine_id: Optional[str] = None
    
    # LinkedIn (Crustdata API)
    crustdata_api_key: Optional[str] = None
    
    # Reddit API
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    reddit_user_agent: Optional[str] = "SignalCollection/1.0"
    
    # Twitter/X API
    twitter_bearer_token: Optional[str] = None
    twitter_api_key: Optional[str] = None
    twitter_api_key_secret: Optional[str] = None
    twitter_access_token: Optional[str] = None
    twitter_access_token_secret: Optional[str] = None
    
    # MCP Configuration
    mcp_endpoint: Optional[str] = None
    
    # Google Sheets Export
    google_sheets_credentials: Optional[str] = None
    
    # Notion Export
    notion_api_key: Optional[str] = None
    notion_api_token: Optional[str] = None  # Alternative name
    notion_database_id: Optional[str] = None
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    
    # Context Path
    default_context_path: str = "./context"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars
    
    @property
    def effective_gemini_key(self) -> Optional[str]:
        """Get Gemini key from either variable name."""
        return self.gemini_api_key or self.gemini_key
    
    @property
    def effective_notion_key(self) -> Optional[str]:
        """Get Notion key from either variable name."""
        return self.notion_api_key or self.notion_api_token


settings = Settings()


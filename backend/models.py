"""Data models for Signal Collection API."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from datetime import datetime
from uuid import uuid4
from enum import Enum


class SignalSource(str, Enum):
    PERPLEXITY = "perplexity"
    GEMINI = "gemini"
    WEBSEARCH = "websearch"
    MCP = "mcp"
    LINKEDIN = "linkedin"
    REDDIT = "reddit"
    TWITTER = "twitter"


class SignalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SignalCategory(str, Enum):
    INDUSTRY_TREND = "industry_trend"
    COMPETITOR_MOVE = "competitor_move"
    MARKET_SHIFT = "market_shift"
    TECHNOLOGY_UPDATE = "technology_update"
    REGULATORY_CHANGE = "regulatory_change"
    CUSTOMER_INSIGHT = "customer_insight"
    CONTENT_OPPORTUNITY = "content_opportunity"
    PARTNERSHIP_OPPORTUNITY = "partnership_opportunity"


class SignalMetadata(BaseModel):
    """Metadata about a signal's origin."""
    source: SignalSource
    source_url: Optional[str] = None
    fetched_at: datetime = Field(default_factory=datetime.now)
    confidence: float = Field(ge=0, le=1)
    query: str


class Signal(BaseModel):
    """A discovered market signal."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    summary: str
    content: str
    category: SignalCategory
    relevance_score: int = Field(ge=0, le=100)
    metadata: SignalMetadata
    status: SignalStatus = SignalStatus.PENDING
    tags: List[str] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class MarketImpact(BaseModel):
    """Market impact assessment."""
    short_term: str
    long_term: str
    risk_level: Literal["low", "medium", "high"]
    opportunity_level: Literal["low", "medium", "high"]


class FounderRelevance(BaseModel):
    """Relevance to a specific founder's content pillar."""
    founder_id: str
    founder_name: str
    pillar_id: str
    pillar_name: str
    relevance_reason: str
    content_angle: str


class SignalEnrichment(BaseModel):
    """Enrichment data for a signal."""
    deep_dive: str
    key_insights: List[str]
    actionable_recommendations: List[str]
    related_topics: List[str]
    sources: List[Dict[str, str]] = []
    market_impact: MarketImpact
    founder_relevance: List[FounderRelevance] = []


class EnrichedSignal(Signal):
    """A signal with enrichment data."""
    enrichment: SignalEnrichment
    enriched_at: datetime = Field(default_factory=datetime.now)


# Request/Response Models

class ResearchRequest(BaseModel):
    """Request to start deep research."""
    context_path: str
    queries: Optional[List[str]] = None
    max_signals: int = 50


class ResearchResponse(BaseModel):
    """Response from deep research."""
    signals: List[Signal]
    total_found: int
    search_duration_ms: int
    sources: List[str]
    query_count: int


class UpdateStatusRequest(BaseModel):
    """Request to update signal status."""
    status: SignalStatus
    notes: Optional[str] = None


class EnrichmentRequest(BaseModel):
    """Request to enrich signals."""
    signal_ids: List[str]
    depth: Literal["standard", "deep"] = "standard"


class ExportRequest(BaseModel):
    """Request to export signals."""
    signal_ids: List[str]
    destination: Literal["google_sheets", "notion"]
    format: Literal["summary", "full"] = "summary"
    include_enrichment: bool = False


class ExportResponse(BaseModel):
    """Response from export operation."""
    success: bool
    destination: str
    url: Optional[str] = None
    exported_count: int
    error: Optional[str] = None


class Stats(BaseModel):
    """Signal statistics."""
    total: int
    pending: int
    approved: int
    rejected: int
    by_category: Dict[str, int]
    by_source: Dict[str, int]
    avg_relevance: float


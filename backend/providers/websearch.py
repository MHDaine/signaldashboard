"""Web search provider using Google Custom Search API."""

import time
import httpx
from typing import Optional
from rich.console import Console

from .base import BaseProvider, ProviderResult, RawSignal
from ..config import settings

console = Console()


class WebSearchProvider(BaseProvider):
    """Google Custom Search provider."""
    
    @property
    def source_name(self) -> str:
        return "websearch"
    
    async def search(self, query: str, context: str) -> ProviderResult:
        """Search using Google Custom Search API."""
        start_time = time.time()
        
        if not settings.google_search_api_key or not settings.google_search_engine_id:
            console.print("[yellow]⚠️ Google Search API not configured, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": settings.google_search_api_key,
                        "cx": settings.google_search_engine_id,
                        "q": query,
                        "num": 10,
                        "dateRestrict": "m3",  # Last 3 months
                    },
                    timeout=30.0
                )
                
                data = response.json()
                items = data.get("items", [])[:5]
                
                signals = [
                    RawSignal(
                        title=item.get("title", ""),
                        summary=item.get("snippet", ""),
                        content=f"{item.get('snippet', '')}\n\nSource: {item.get('link', '')}",
                        source_url=item.get("link"),
                        confidence=0.7,
                    )
                    for item in items
                ]
                
                return ProviderResult(
                    signals=signals,
                    source=self.source_name,
                    query=query,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
        
        except Exception as e:
            console.print(f"[red]❌ Web search error: {e}[/red]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query=query,
                duration_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
    
    def _get_mock_result(self, query: str, start_time: float) -> ProviderResult:
        """Return mock data for testing."""
        return ProviderResult(
            signals=[
                RawSignal(
                    title="Marketing Agency Consolidation Trend Continues",
                    summary="Industry report shows 23% of marketing agencies merged or acquired in 2025, with AI capabilities being the primary driver of deal value.",
                    content="""A comprehensive industry analysis reveals ongoing consolidation in the marketing services sector. 23% of agencies either merged or were acquired in the past year. AI capabilities now account for 40% of agency valuation in M&A deals. This trend creates opportunities for AI-native marketing platforms to capture displaced enterprise clients.""",
                    source_url="https://example.com/agency-report-2026",
                    confidence=0.75,
                ),
                RawSignal(
                    title="CMOs Prioritize Marketing Efficiency Over Growth",
                    summary="Survey of 500 CMOs reveals efficiency metrics now outweigh growth metrics in performance reviews, signaling budget optimization focus.",
                    content="""A new survey of 500 enterprise CMOs shows a significant shift in priorities. 67% now report that efficiency metrics (cost per acquisition, marketing ROI) are weighted more heavily than pure growth metrics in their performance reviews. This represents a reversal from 2024 patterns and suggests increased scrutiny on marketing spend.""",
                    source_url="https://example.com/cmo-survey-2026",
                    confidence=0.72,
                ),
            ],
            source=self.source_name,
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
        )


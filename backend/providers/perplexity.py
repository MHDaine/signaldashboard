"""Perplexity AI provider for real-time web research."""

import time
import httpx
from typing import Optional
from rich.console import Console

from .base import BaseProvider, ProviderResult, RawSignal
from ..config import settings

console = Console()


class PerplexityProvider(BaseProvider):
    """Perplexity AI research provider."""
    
    @property
    def source_name(self) -> str:
        return "perplexity"
    
    async def search(self, query: str, context: str) -> ProviderResult:
        """Search using Perplexity AI."""
        start_time = time.time()
        
        if not settings.perplexity_api_key:
            console.print("[yellow]⚠️ Perplexity API key not configured, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.perplexity_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {
                                "role": "system",
                                "content": f"""You are a research analyst finding RECENT NEWS that would be relevant for thought leadership content.

COMPANY CONTEXT:
{context}

YOUR TASK:
Find the most recent news, announcements, and developments (from the past 7-30 days) that:
1. MH-1's founders could comment on in LinkedIn posts or articles
2. Would be interesting to VPs of Marketing, CMOs, and startup CEOs
3. Relates to AI marketing, marketing automation, B2B SaaS, or agency disruption
4. Contains specific data points, statistics, or quotes when possible

For EACH finding, provide:
- A specific, descriptive headline
- A 2-3 sentence summary with KEY FACTS and DATA POINTS
- Why this matters for marketing leaders
- Source attribution if available

Focus on ACTIONABLE news that sparks conversation, not general trends."""
                            },
                            {"role": "user", "content": f"Find recent news about: {query}"}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 2000,
                    },
                    timeout=30.0
                )
                
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Extract citations (source URLs) from Perplexity response
                citations = data.get("citations", [])
                
                signals = self.parse_signals_from_text(content, query)
                
                # Attach citations to signals (distribute URLs across signals)
                for i, signal in enumerate(signals):
                    if i < len(citations):
                        signal.source_url = citations[i]
                    elif citations:
                        # If more signals than citations, reuse citations
                        signal.source_url = citations[i % len(citations)]
                
                return ProviderResult(
                    signals=signals,
                    source=self.source_name,
                    query=query,
                    duration_ms=int((time.time() - start_time) * 1000),
                    citations=citations,  # Store all citations
                )
        
        except Exception as e:
            console.print(f"[red]❌ Perplexity error: {e}[/red]")
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
                    title="AI Marketing Adoption Accelerates in 2026",
                    summary="According to recent data, 85% of marketing teams are now using AI tools daily, up from 65% in 2025. The shift is driven by improved ROI measurement capabilities.",
                    content="""Recent analysis shows that AI marketing adoption has reached a tipping point. 85% of marketing teams now use AI tools daily for content generation, campaign optimization, and customer analytics. The key drivers include: better integration capabilities, clearer ROI metrics, and executive mandates for efficiency gains. Companies report an average 3.2x improvement in content output with similar quality benchmarks.""",
                    confidence=0.85,
                ),
                RawSignal(
                    title="Marketing Attribution Models Evolving Post-Cookie",
                    summary="New attribution frameworks emerge as third-party cookies phase out. Marketing mix modeling and incrementality testing see 200% increase in adoption.",
                    content="""The deprecation of third-party cookies has accelerated the adoption of alternative attribution methods. Marketing Mix Modeling (MMM) adoption increased 200% year-over-year. Companies are combining MMM with incrementality testing and first-party data strategies. Leaders like MH-1 and similar platforms are capitalizing on this shift by offering integrated measurement solutions.""",
                    confidence=0.78,
                ),
            ],
            source=self.source_name,
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
        )


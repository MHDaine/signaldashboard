"""Google Gemini provider for AI-powered research."""

import time
from typing import Optional
from rich.console import Console

from .base import BaseProvider, ProviderResult, RawSignal
from ..config import settings

console = Console()


class GeminiProvider(BaseProvider):
    """Google Gemini research provider."""
    
    @property
    def source_name(self) -> str:
        return "gemini"
    
    async def search(self, query: str, context: str) -> ProviderResult:
        """Search using Google Gemini."""
        start_time = time.time()
        
        gemini_key = settings.effective_gemini_key
        if not gemini_key:
            console.print("[yellow]⚠️ Gemini API key not configured, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            prompt = f"""You are a research analyst helping MH-1 (MarketerHire) find recent news for thought leadership content.

COMPANY CONTEXT:
{context}

SEARCH TOPIC: {query}

Find 3-5 RECENT news items, announcements, or developments that MH-1's founders could create thought leadership content about. Consider:

TARGET AUDIENCE (who will read the content):
- VPs of Marketing struggling with AI adoption and vendor management
- First-time CMOs trying to prove ROI in their first 90 days
- Startup CEOs who think marketing is a "black box"

FOUNDER PERSPECTIVES TO MATCH:
- Chris Toy: "Attribution is dead" - skeptical of measurement, pro-fundamentals
- Cameron Rzonca: "AI systems beat AI tools" - integration over procurement  
- Nikhil Arora: "P&L-driven growth" - marketing must own revenue outcomes
- Raaja Nemani: "Community as moat" - talent networks and relationships matter

For each finding, provide:
## [Specific News Headline]
**Summary**: 2-3 sentences with specific facts, data points, or quotes
**Why This Matters**: How this affects marketing leaders and why they should care
**Thought Leadership Angle**: Which founder's POV this aligns with and a potential content hook

Focus on news that would spark engagement on LinkedIn - controversial, data-backed, or contrarian takes welcome."""
            
            response = await model.generate_content_async(prompt)
            content = response.text
            signals = self.parse_signals_from_text(content, query)
            
            return ProviderResult(
                signals=signals,
                source=self.source_name,
                query=query,
                duration_ms=int((time.time() - start_time) * 1000),
            )
        
        except Exception as e:
            console.print(f"[red]❌ Gemini error: {e}[/red]")
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
                    title="Enterprise AI Marketing Budgets Surge",
                    summary="Analysis indicates enterprise marketing teams are allocating 35% more budget to AI-powered solutions compared to last year, with a focus on workflow automation.",
                    content="""Enterprise marketing departments are significantly increasing their AI investments. Budget allocations for AI marketing tools have grown 35% YoY. Key investment areas include: automated content generation (45% of AI spend), predictive analytics (30%), and workflow automation (25%). Mid-market companies are following enterprise patterns with a 6-month lag.""",
                    confidence=0.82,
                ),
                RawSignal(
                    title="Fractional Marketing Leadership Growing",
                    summary="The fractional CMO market is projected to reach $2.8B by 2027, driven by venture-backed companies seeking enterprise expertise without full-time costs.",
                    content="""The fractional and on-demand marketing leadership market continues to expand. Current projections show the market reaching $2.8B by 2027. Growth drivers include: (1) Venture-backed companies with $10-50M ARR seeking enterprise-grade strategy, (2) AI enabling smaller teams to execute at scale, (3) Economic uncertainty driving preference for variable costs over headcount.""",
                    confidence=0.79,
                ),
            ],
            source=self.source_name,
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
        )


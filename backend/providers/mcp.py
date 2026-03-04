"""MCP (Model Context Protocol) provider for extensible research."""

import time
import httpx
from typing import Optional
from rich.console import Console

from .base import BaseProvider, ProviderResult, RawSignal
from ..config import settings

console = Console()


class MCPProvider(BaseProvider):
    """MCP (Model Context Protocol) research provider."""
    
    @property
    def source_name(self) -> str:
        return "mcp"
    
    async def search(self, query: str, context: str) -> ProviderResult:
        """Search using MCP endpoint."""
        start_time = time.time()
        
        if not settings.mcp_endpoint:
            console.print("[yellow]⚠️ MCP endpoint not configured, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.mcp_endpoint,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "research",
                            "arguments": {
                                "query": query,
                                "context": context,
                                "depth": "deep",
                            },
                        },
                        "id": int(time.time() * 1000),
                    },
                    timeout=30.0
                )
                
                data = response.json()
                content = data.get("result", {}).get("content", [{}])[0].get("text", "")
                signals = self.parse_signals_from_text(content, query)
                
                return ProviderResult(
                    signals=signals,
                    source=self.source_name,
                    query=query,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
        
        except Exception as e:
            console.print(f"[red]❌ MCP error: {e}[/red]")
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
                    title="LinkedIn Algorithm Favors Long-Form Thought Leadership",
                    summary="Platform analysis shows 40% increase in reach for posts over 1,200 characters with original POV statements and data citations.",
                    content="""Deep platform analysis reveals LinkedIn's algorithm significantly favors long-form thought leadership content. Posts over 1,200 characters with original POV statements see 40% more reach than shorter content. Additional ranking factors include: engagement in first 90 minutes, comment quality over quantity, and connection with trending professional topics.""",
                    confidence=0.88,
                ),
                RawSignal(
                    title="B2B Buyer Journey Now 70% Digital",
                    summary="Research indicates B2B buyers complete 70% of their evaluation process through digital channels before engaging sales, creating content marketing opportunities.",
                    content="""Comprehensive buyer journey mapping shows B2B buyers now complete 70% of their evaluation digitally. Key touchpoints include: vendor content (45%), peer reviews (30%), social proof (15%), analyst reports (10%). This shift emphasizes the importance of thought leadership and digital presence for companies like MH-1 targeting enterprise decision-makers.""",
                    confidence=0.84,
                ),
            ],
            source=self.source_name,
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
        )


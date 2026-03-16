"""LinkedIn provider for thought leader and keyword signal collection."""

import time
import httpx
from typing import Optional, List
from datetime import datetime
from rich.console import Console

from .base import BaseProvider, ProviderResult, RawSignal
from ..config import settings

console = Console()


class LinkedInProvider(BaseProvider):
    """LinkedIn research provider using Crustdata API."""
    
    API_URL = "https://api.crustdata.com/screener/linkedin_posts/keyword_search/"
    
    @property
    def source_name(self) -> str:
        return "linkedin"
    
    async def search(self, query: str, context: str) -> ProviderResult:
        """Search LinkedIn posts using Crustdata API."""
        start_time = time.time()
        
        api_key = settings.crustdata_api_key
        if not api_key:
            console.print("[yellow]⚠️ Crustdata API key not configured, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.API_URL,
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    json={
                        "keyword": query,
                        "limit": 50,
                        "date_posted": "past-week",
                        "sort_by": "relevance",
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Handle both list and dict responses
                    if isinstance(data, list):
                        posts = data
                    else:
                        posts = data.get("posts", [])
                    
                    signals = []
                    for post in posts[:10]:  # Limit to 10 best posts
                        if not isinstance(post, dict):
                            continue
                        actor_name = post.get("actor_name", "Unknown")
                        text = post.get("text", "")[:500]
                        share_url = post.get("share_url", "")
                        date_posted = post.get("date_posted", "")
                        reactions = post.get("total_reactions", 0)
                        comments = post.get("total_comments", 0)
                        
                        # Skip low-engagement posts
                        if reactions + comments < 5:
                            continue
                        
                        # Generate title from first line or actor
                        first_line = text.split('\n')[0][:100] if text else ""
                        title = first_line if len(first_line) > 20 else f"{actor_name}: {first_line}"
                        
                        signals.append(RawSignal(
                            title=title,
                            summary=f"{actor_name} ({reactions} reactions, {comments} comments): {text[:200]}...",
                            content=f"**Author**: {actor_name}\n**Posted**: {date_posted}\n**Engagement**: {reactions} reactions, {comments} comments\n\n{text}",
                            source_url=share_url,
                            published_date=date_posted,
                            confidence=min(0.5 + (reactions / 100) + (comments / 50), 0.95),
                        ))
                    
                    return ProviderResult(
                        signals=signals,
                        source=self.source_name,
                        query=query,
                        duration_ms=int((time.time() - start_time) * 1000),
                    )
                else:
                    console.print(f"[red]❌ LinkedIn API error: {response.status_code}[/red]")
                    return self._get_mock_result(query, start_time)
        
        except Exception as e:
            console.print(f"[red]❌ LinkedIn error: {e}[/red]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query=query,
                duration_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
    
    async def search_thought_leaders(
        self, 
        profile_urls: List[str], 
        context: str
    ) -> ProviderResult:
        """Fetch posts from specific LinkedIn thought leaders."""
        start_time = time.time()
        
        api_key = settings.crustdata_api_key
        if not api_key:
            console.print("[yellow]⚠️ Crustdata API key not configured[/yellow]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query="thought_leaders",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.API_URL,
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "filters": [{
                            "filter_type": "MEMBER",
                            "type": "in",
                            "value": profile_urls
                        }],
                        "date_posted": "past-week",
                        "limit": 100
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    posts = data.get("posts", [])
                    
                    signals = []
                    for post in posts:
                        actor_name = post.get("actor_name", "Unknown")
                        text = post.get("text", "")
                        share_url = post.get("share_url", "")
                        
                        signals.append(RawSignal(
                            title=f"{actor_name}: {text[:80]}...",
                            summary=text[:300],
                            content=text,
                            source_url=share_url,
                            confidence=0.85,  # High confidence for thought leaders
                        ))
                    
                    return ProviderResult(
                        signals=signals,
                        source=self.source_name,
                        query="thought_leaders",
                        duration_ms=int((time.time() - start_time) * 1000),
                    )
                    
        except Exception as e:
            console.print(f"[red]❌ LinkedIn thought leaders error: {e}[/red]")
        
        return ProviderResult(
            signals=[],
            source=self.source_name,
            query="thought_leaders",
            duration_ms=int((time.time() - start_time) * 1000),
        )
    
    def _get_mock_result(self, query: str, start_time: float) -> ProviderResult:
        """Return mock data for testing."""
        return ProviderResult(
            signals=[
                RawSignal(
                    title="CMO shares: Why AI Marketing Systems Beat Point Solutions",
                    summary="After 6 months testing 12 AI tools, our marketing team consolidated to one integrated system. Results: 3x output, 40% cost reduction, and finally measurable ROI.",
                    content="""After 6 months testing 12 different AI tools, our marketing team made a dramatic shift. We consolidated everything into one integrated AI marketing system.

The results speak for themselves:
- 3x content output
- 40% reduction in marketing tech spend
- Finally able to measure actual ROI

The lesson? Tools are commodities. Systems are competitive advantages.

What's your experience with AI tool consolidation?""",
                    source_url="https://linkedin.com/posts/example-cmo-post",
                    confidence=0.82,
                ),
                RawSignal(
                    title="VP Growth: The Death of Last-Touch Attribution",
                    summary="We stopped using last-touch attribution 3 months ago. Here's what we learned about marketing measurement in a post-cookie world.",
                    content="""Hot take: Last-touch attribution is officially dead.

We stopped using it 3 months ago at our Series B startup. Here's what we learned:

1. Multi-touch models still require too much data we can't collect
2. Marketing Mix Modeling is making a comeback (for good reason)
3. The best metric? Incrementality testing

Our CAC dropped 22% after we stopped optimizing for attributed conversions.

Anyone else making this shift?""",
                    source_url="https://linkedin.com/posts/example-vp-post",
                    confidence=0.78,
                ),
            ],
            source=self.source_name,
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
        )


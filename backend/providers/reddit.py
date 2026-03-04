"""Reddit provider for subreddit and keyword signal collection."""

import time
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
from rich.console import Console

from .base import BaseProvider, ProviderResult, RawSignal
from ..config import settings

console = Console()


class RedditProvider(BaseProvider):
    """Reddit research provider using PRAW."""
    
    # Default subreddits relevant to marketing/B2B/SaaS
    DEFAULT_SUBREDDITS = [
        "marketing",
        "digitalmarketing", 
        "SaaS",
        "startups",
        "Entrepreneur",
        "content_marketing",
        "socialmedia",
        "PPC",
        "SEO",
        "growthmarketing",
    ]
    
    @property
    def source_name(self) -> str:
        return "reddit"
    
    async def search(self, query: str, context: str) -> ProviderResult:
        """Search Reddit for relevant posts."""
        start_time = time.time()
        
        client_id = settings.reddit_client_id
        client_secret = settings.reddit_client_secret
        
        if not client_id or not client_secret:
            console.print("[yellow]⚠️ Reddit API not configured, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        
        try:
            # Import praw only when needed
            import praw
            
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=settings.reddit_user_agent or "SignalCollection/1.0",
            )
            
            signals = []
            cutoff_date = datetime.now() - timedelta(days=30)
            
            # Search across relevant subreddits
            subreddits_str = "+".join(self.DEFAULT_SUBREDDITS[:5])
            subreddit = reddit.subreddit(subreddits_str)
            
            # Run in thread pool since PRAW is synchronous
            loop = asyncio.get_event_loop()
            posts = await loop.run_in_executor(
                None,
                lambda: list(subreddit.search(query, limit=20, time_filter="month", sort="relevance"))
            )
            
            for post in posts:
                post_date = datetime.fromtimestamp(post.created_utc)
                
                if post_date < cutoff_date:
                    continue
                
                # Skip low-engagement posts
                if post.score < 5:
                    continue
                
                signals.append(RawSignal(
                    title=post.title,
                    summary=f"r/{post.subreddit} | {post.score} upvotes, {post.num_comments} comments | {post.selftext[:200] if post.selftext else post.url}",
                    content=f"**Subreddit**: r/{post.subreddit}\n**Author**: u/{post.author}\n**Score**: {post.score} upvotes\n**Comments**: {post.num_comments}\n\n{post.selftext[:1000] if post.selftext else f'Link: {post.url}'}",
                    source_url=f"https://reddit.com{post.permalink}",
                    published_date=post_date.strftime("%Y-%m-%d"),
                    confidence=min(0.5 + (post.score / 200) + (post.num_comments / 100), 0.92),
                ))
            
            return ProviderResult(
                signals=signals[:10],  # Limit to top 10
                source=self.source_name,
                query=query,
                duration_ms=int((time.time() - start_time) * 1000),
            )
        
        except ImportError:
            console.print("[yellow]⚠️ PRAW not installed, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        except Exception as e:
            console.print(f"[red]❌ Reddit error: {e}[/red]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query=query,
                duration_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
    
    async def search_subreddits(
        self, 
        subreddits: List[str],
        keywords: List[str],
        days_back: int = 30
    ) -> ProviderResult:
        """Search specific subreddits for keywords."""
        start_time = time.time()
        
        client_id = settings.reddit_client_id
        client_secret = settings.reddit_client_secret
        
        if not client_id or not client_secret:
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query="subreddits",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        
        try:
            import praw
            
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=settings.reddit_user_agent or "SignalCollection/1.0",
            )
            
            signals = []
            cutoff_date = datetime.now() - timedelta(days=days_back)
            seen_ids = set()
            
            loop = asyncio.get_event_loop()
            
            for subreddit_name in subreddits:
                sub = reddit.subreddit(subreddit_name)
                
                for keyword in keywords:
                    posts = await loop.run_in_executor(
                        None,
                        lambda: list(sub.search(keyword, limit=10, time_filter="month"))
                    )
                    
                    for post in posts:
                        if post.id in seen_ids:
                            continue
                        seen_ids.add(post.id)
                        
                        post_date = datetime.fromtimestamp(post.created_utc)
                        if post_date < cutoff_date:
                            continue
                        
                        signals.append(RawSignal(
                            title=post.title,
                            summary=f"r/{post.subreddit} | {post.score} upvotes | {post.selftext[:150] if post.selftext else ''}",
                            content=post.selftext[:1000] if post.selftext else post.url,
                            source_url=f"https://reddit.com{post.permalink}",
                            confidence=min(0.5 + (post.score / 200), 0.9),
                        ))
            
            return ProviderResult(
                signals=signals,
                source=self.source_name,
                query="subreddits",
                duration_ms=int((time.time() - start_time) * 1000),
            )
            
        except Exception as e:
            console.print(f"[red]❌ Reddit subreddits error: {e}[/red]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query="subreddits",
                duration_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
    
    def _get_mock_result(self, query: str, start_time: float) -> ProviderResult:
        """Return mock data for testing."""
        return ProviderResult(
            signals=[
                RawSignal(
                    title="[Discussion] Our experience switching from 5 marketing tools to one AI system",
                    summary="r/SaaS | 234 upvotes, 89 comments | We made the switch 4 months ago. Here's the honest breakdown of what worked and what didn't...",
                    content="""**Subreddit**: r/SaaS
**Author**: u/marketingops_lead
**Score**: 234 upvotes
**Comments**: 89

We made the switch from using Jasper + Surfer + Clearscope + HubSpot AI + ChatGPT to a single integrated system 4 months ago.

**What worked:**
- Single source of truth for all content
- Actual workflow automation (not just tools)
- Way easier onboarding for new team members

**What didn't:**
- Learning curve was steeper than expected
- Had to rebuild some custom workflows
- Initial cost was higher (but ROI came in month 3)

Would I do it again? 100%.

AMA about our experience.""",
                    source_url="https://reddit.com/r/SaaS/comments/example1",
                    confidence=0.85,
                ),
                RawSignal(
                    title="Fractional CMOs - how are you handling the AI transformation requests?",
                    summary="r/marketing | 156 upvotes, 67 comments | Every client now wants 'AI strategy' but most don't know what that means...",
                    content="""**Subreddit**: r/marketing
**Author**: u/fractional_cmo
**Score**: 156 upvotes
**Comments**: 67

I'm a fractional CMO working with 4 B2B SaaS companies. In the past 6 months, every single board meeting includes questions about "our AI strategy."

The problem? Most CEOs/boards don't know what they're actually asking for. They've seen the headlines about ChatGPT and assume their marketing team should be "using AI" but can't articulate what success looks like.

What I've started doing:
1. Audit their current tool stack for AI capabilities they're not using
2. Identify 3 specific workflows where AI can save time
3. Set measurable goals (content output, campaign velocity, etc.)
4. Partner with a system provider vs. buying more point solutions

Anyone else dealing with this "AI mandate" from the top?""",
                    source_url="https://reddit.com/r/marketing/comments/example2",
                    confidence=0.82,
                ),
            ],
            source=self.source_name,
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
        )


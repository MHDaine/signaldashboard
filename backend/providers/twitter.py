"""Twitter/X provider for keyword signal collection."""

import time
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from rich.console import Console

from .base import BaseProvider, ProviderResult, RawSignal
from ..config import settings

console = Console()


class TwitterProvider(BaseProvider):
    """Twitter/X research provider using Tweepy."""
    
    @property
    def source_name(self) -> str:
        return "twitter"
    
    async def search(self, query: str, context: str) -> ProviderResult:
        """Search Twitter for relevant tweets."""
        start_time = time.time()
        
        bearer_token = settings.twitter_bearer_token
        
        if not bearer_token:
            console.print("[yellow]⚠️ Twitter API not configured, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        
        try:
            # Import tweepy only when needed
            import tweepy
            
            client = tweepy.Client(
                bearer_token=bearer_token,
                wait_on_rate_limit=True
            )
            
            # Build search query with quality filters (Basic tier compatible)
            search_query = f"{query} lang:en -is:retweet"
            
            # Search last 7 days (Basic tier limit)
            start_time_search = datetime.now(timezone.utc) - timedelta(days=7)
            
            # Run in thread pool since Tweepy can block
            loop = asyncio.get_event_loop()
            
            def fetch_tweets():
                tweets = []
                for tweet in tweepy.Paginator(
                    client.search_recent_tweets,
                    query=search_query,
                    start_time=start_time_search,
                    tweet_fields=['id', 'text', 'created_at', 'author_id', 'public_metrics'],
                    user_fields=['username', 'name', 'verified', 'public_metrics'],
                    expansions=['author_id'],
                    max_results=50
                ).flatten(limit=30):
                    tweets.append(tweet)
                return tweets
            
            tweets = await loop.run_in_executor(None, fetch_tweets)
            
            signals = []
            for tweet in tweets:
                metrics = tweet.public_metrics if hasattr(tweet, 'public_metrics') else {}
                likes = metrics.get('like_count', 0)
                retweets = metrics.get('retweet_count', 0)
                replies = metrics.get('reply_count', 0)
                
                # Calculate engagement score
                engagement = likes + (retweets * 2) + (replies * 3)
                
                signals.append(RawSignal(
                    title=tweet.text[:100] + "..." if len(tweet.text) > 100 else tweet.text,
                    summary=f"❤️ {likes} | 🔄 {retweets} | 💬 {replies} | {tweet.text[:200]}",
                    content=f"**Engagement**: {likes} likes, {retweets} retweets, {replies} replies\n\n{tweet.text}",
                    source_url=f"https://twitter.com/i/status/{tweet.id}",
                    published_date=tweet.created_at.strftime("%Y-%m-%d") if tweet.created_at else "",
                    confidence=min(0.5 + (engagement / 500), 0.9),
                ))
            
            # Sort by confidence (engagement)
            signals.sort(key=lambda x: x.confidence, reverse=True)
            
            return ProviderResult(
                signals=signals[:10],  # Top 10 by engagement
                source=self.source_name,
                query=query,
                duration_ms=int((time.time() - start_time) * 1000),
            )
        
        except ImportError:
            console.print("[yellow]⚠️ Tweepy not installed, using mock data[/yellow]")
            return self._get_mock_result(query, start_time)
        except Exception as e:
            console.print(f"[red]❌ Twitter error: {e}[/red]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query=query,
                duration_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
    
    async def search_hashtags(
        self,
        hashtags: List[str],
        min_engagement: int = 10
    ) -> ProviderResult:
        """Search specific hashtags."""
        start_time = time.time()
        
        # Build hashtag query
        hashtag_query = " OR ".join([f"#{tag}" for tag in hashtags])
        
        return await self.search(hashtag_query, "")
    
    def _get_mock_result(self, query: str, start_time: float) -> ProviderResult:
        """Return mock data for testing."""
        return ProviderResult(
            signals=[
                RawSignal(
                    title="🔥 Unpopular opinion: The 'AI marketing tools' era is ending. The 'AI marketing systems' era is beginning...",
                    summary="❤️ 847 | 🔄 234 | 💬 89 | Thread on why integration matters more than individual tool features",
                    content="""**Engagement**: 847 likes, 234 retweets, 89 replies

🔥 Unpopular opinion: The 'AI marketing tools' era is ending. The 'AI marketing systems' era is beginning.

Here's why (thread 🧵):

1/ Most marketing teams now use 5-12 AI tools. ChatGPT, Jasper, Midjourney, etc.

But they're all disconnected. Copy-paste between tools. Manual handoffs. No unified data.

2/ The winners in 2026 won't be the companies with the best individual tools.

They'll be the ones with the best SYSTEMS that connect tools + humans + workflows.

3/ Think about it: What good is AI-generated content if it doesn't connect to your CRM, analytics, and campaign management?

The answer: Not much.

4/ This is why we're seeing a shift from "tool buyers" to "system builders."

Mid-market companies are consolidating their stacks faster than enterprises.

5/ The companies that figure this out first will have a 12-18 month head start on their competitors.

What's your take? Are you still buying tools or building systems?""",
                    source_url="https://twitter.com/example/status/123456789",
                    confidence=0.88,
                ),
                RawSignal(
                    title="Just saw data from a CMO survey: 72% say 'AI strategy' is a top priority, but only 18% can explain what that means...",
                    summary="❤️ 523 | 🔄 178 | 💬 67 | The gap between AI ambition and execution is widening",
                    content="""**Engagement**: 523 likes, 178 retweets, 67 replies

Just saw data from a CMO survey:

72% say "AI strategy" is a top priority

But only 18% can explain what that actually means for their team

The gap between AI ambition and AI execution is widening.

Most teams are:
- Buying tools they don't use fully
- Creating content without workflow integration
- Missing the attribution entirely

The solution isn't more tools. It's better systems + the right people to run them.

Who's actually doing this well?""",
                    source_url="https://twitter.com/example/status/987654321",
                    confidence=0.84,
                ),
            ],
            source=self.source_name,
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
        )


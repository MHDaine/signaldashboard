#!/usr/bin/env python3
"""
Twitter/X Keyword Search Script

Searches recent tweets (last 7 days) based on keywords from sources.json.
Uses X API v2 Recent Search endpoint.

Usage:
    python scripts/twitter_keyword_search.py                    # Search all keywords
    python scripts/twitter_keyword_search.py --keywords "AI marketing,growth"
    python scripts/twitter_keyword_search.py --limit 50         # Limit per keyword
    python scripts/twitter_keyword_search.py --json             # Output JSON to stdout
    python scripts/twitter_keyword_search.py --save             # Save to file
"""

import sys
import os
import json
import argparse
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()

console = Console()

# Configuration
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN", "")
TWITTER_API_URL = "https://api.x.com/2/tweets/search/recent"
SOURCES_FILE = "sources.json"

# Fields to request
TWEET_FIELDS = "created_at,public_metrics,author_id,conversation_id,lang"
USER_FIELDS = "name,username,public_metrics,description,verified"
EXPANSIONS = "author_id"


def load_sources() -> Dict[str, Any]:
    """Load sources.json configuration."""
    sources_path = Path(__file__).parent.parent / SOURCES_FILE
    
    if not sources_path.exists():
        console.print(f"[red]Error: {SOURCES_FILE} not found[/red]")
        sys.exit(1)
    
    with open(sources_path, 'r') as f:
        return json.load(f)


async def search_twitter_keyword(
    keyword: str,
    max_results: int = 100,
    next_token: Optional[str] = None
) -> Dict[str, Any]:
    """Search Twitter for tweets matching a keyword."""
    
    if not TWITTER_BEARER_TOKEN:
        console.print("[red]Error: TWITTER_BEARER_TOKEN not configured[/red]")
        return {"tweets": [], "users": {}, "next_token": None}
    
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Build query - exclude retweets for original content
    query = f"{keyword} -is:retweet lang:en"
    
    params = {
        "query": query,
        "max_results": min(max_results, 100),  # API max is 100 per request
        "tweet.fields": TWEET_FIELDS,
        "user.fields": USER_FIELDS,
        "expansions": EXPANSIONS,
    }
    
    if next_token:
        params["next_token"] = next_token
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                TWITTER_API_URL,
                headers=headers,
                params=params,
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract tweets and users
                tweets = data.get("data", [])
                
                # Build user lookup from includes
                users = {}
                includes = data.get("includes", {})
                for user in includes.get("users", []):
                    users[user["id"]] = user
                
                # Get next_token for pagination
                meta = data.get("meta", {})
                next_token = meta.get("next_token")
                
                return {
                    "tweets": tweets,
                    "users": users,
                    "next_token": next_token
                }
            
            elif response.status_code == 429:
                # Rate limited - check reset time
                reset_time = response.headers.get("x-rate-limit-reset")
                if reset_time:
                    wait_seconds = int(reset_time) - int(datetime.now().timestamp())
                    console.print(f"[yellow]⚠️ Rate limited. Resets in {wait_seconds}s[/yellow]")
                else:
                    console.print(f"[yellow]⚠️ Rate limited for '{keyword}'[/yellow]")
                return {"tweets": [], "users": {}, "next_token": None}
            
            else:
                error_text = response.text[:300]
                console.print(f"[red]Error {response.status_code} for '{keyword}': {error_text}[/red]")
                return {"tweets": [], "users": {}, "next_token": None}
    
    except Exception as e:
        console.print(f"[red]Error searching '{keyword}': {e}[/red]")
        return {"tweets": [], "users": {}, "next_token": None}


def transform_to_signal(
    tweet: Dict[str, Any],
    user: Dict[str, Any],
    keyword: str
) -> Dict[str, Any]:
    """Transform a tweet to signal format."""
    
    tweet_id = tweet.get("id", "")
    text = tweet.get("text", "")
    created_at = tweet.get("created_at", "")
    
    # Get metrics
    metrics = tweet.get("public_metrics", {})
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    replies = metrics.get("reply_count", 0)
    quotes = metrics.get("quote_count", 0)
    impressions = metrics.get("impression_count", 0)
    
    # User info
    username = user.get("username", "unknown")
    display_name = user.get("name", username)
    user_metrics = user.get("public_metrics", {})
    followers = user_metrics.get("followers_count", 0)
    verified = user.get("verified", False)
    
    # Build tweet URL
    tweet_url = f"https://x.com/{username}/status/{tweet_id}"
    
    return {
        "id": tweet_id,
        "type": "twitter-keyword",
        "author": display_name,
        "author_handle": f"@{username}",
        "author_followers": followers,
        "author_verified": verified,
        "title": text[:100] if text else "",
        "content": text,
        "date_posted": created_at,
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "url": tweet_url,
        "matched_keyword": keyword,
        "engagement": {
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "quotes": quotes,
            "impressions": impressions,
            "total": likes + retweets + replies + quotes
        },
        "status": "unused",
    }


async def collect_twitter_keywords(
    keywords: List[str],
    limit_per_keyword: int = 100,
    max_total: int = None
) -> List[Dict[str, Any]]:
    """Collect tweets for multiple keywords.
    
    Args:
        keywords: List of search keywords.
        limit_per_keyword: Max tweets to fetch per keyword.
        max_total: Overall cap on total signals returned. If set, collection
                   stops early once this many signals are gathered.
    """
    
    all_signals = []
    seen_ids = set()
    
    # If max_total is set, adjust per-keyword limit so we don't massively overshoot
    effective_per_kw = limit_per_keyword
    if max_total:
        effective_per_kw = min(limit_per_keyword, max(10, max_total // max(len(keywords), 1)))
    
    console.print(Panel(
        f'[bold cyan]Twitter/X Keyword Search[/bold cyan]\n\n'
        f'Keywords: {len(keywords)}\n'
        f'Limit per keyword: {effective_per_kw}\n'
        f'Total cap: {max_total or "none"}\n'
        f'Date range: Last 7 days (API limit)',
        border_style='cyan'
    ))
    
    for i, keyword in enumerate(keywords, 1):
        # Check total cap before starting a new keyword
        if max_total and len(all_signals) >= max_total:
            console.print(f"[dim]   Reached total cap ({max_total}), skipping remaining keywords[/dim]")
            break
        
        console.print(f"\n[yellow][{i}/{len(keywords)}] Searching: \"{keyword}\"[/yellow]")
        
        collected = 0
        next_token = None
        keyword_signals = []
        
        # How many more we can collect for this keyword
        keyword_budget = effective_per_kw
        if max_total:
            keyword_budget = min(effective_per_kw, max_total - len(all_signals))
        
        # Paginate if needed
        while collected < keyword_budget:
            remaining = keyword_budget - collected
            # API requires max_results between 10-100
            batch_size = max(10, min(remaining, 100))
            
            result = await search_twitter_keyword(keyword, batch_size, next_token)
            tweets = result["tweets"]
            users = result["users"]
            next_token = result["next_token"]
            
            if not tweets:
                break
            
            for tweet in tweets:
                if collected >= keyword_budget:
                    break
                
                author_id = tweet.get("author_id", "")
                user = users.get(author_id, {})
                signal = transform_to_signal(tweet, user, keyword)
                
                # Deduplicate by tweet ID
                if signal["id"] and signal["id"] not in seen_ids:
                    seen_ids.add(signal["id"])
                    keyword_signals.append(signal)
                    collected += 1
            
            if not next_token:
                break
            
            # Small delay between pagination requests
            await asyncio.sleep(0.5)
        
        all_signals.extend(keyword_signals)
        console.print(f"   [green]✓ Found {collected} tweets[/green]")
        
        # Delay between keywords to respect rate limits
        await asyncio.sleep(1)
    
    # Final enforcement of total cap
    if max_total and len(all_signals) > max_total:
        all_signals = all_signals[:max_total]
    
    return all_signals


def print_summary(signals: List[Dict[str, Any]]):
    """Print collection summary."""
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ COLLECTION COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Signals: [bold]{len(signals)}[/bold]\n")
    
    if not signals:
        console.print("[yellow]No tweets found for the specified keywords.[/yellow]")
        return
    
    # Group by keyword
    by_keyword = {}
    for s in signals:
        kw = s.get("matched_keyword", "unknown")
        by_keyword[kw] = by_keyword.get(kw, 0) + 1
    
    table = Table(title="Tweets by Keyword", show_header=True, header_style="bold magenta")
    table.add_column("Keyword", width=30)
    table.add_column("Count", width=10, justify="center")
    
    for kw, count in sorted(by_keyword.items(), key=lambda x: x[1], reverse=True):
        table.add_row(kw, str(count))
    
    console.print(table)
    
    # Show top tweets by engagement
    console.print("\n[bold]Top Tweets by Engagement:[/bold]\n")
    
    sorted_signals = sorted(
        signals, 
        key=lambda x: x['engagement']['total'],
        reverse=True
    )
    
    for i, s in enumerate(sorted_signals[:5], 1):
        engagement = s['engagement']
        console.print(f"[magenta]{i}. {s['author']} ({s['author_handle']})[/magenta]")
        console.print(f"   ❤️ {engagement['likes']} | 🔁 {engagement['retweets']} | 💬 {engagement['replies']}")
        console.print(f"   {s['title'][:70]}...")
        console.print(f"   [cyan]🔗 {s['url']}[/cyan]")
        console.print()


def output_json(signals: List[Dict[str, Any]]):
    """Output signals as JSON to stdout."""
    output = {
        "platform": "twitter",
        "source_type": "keyword-search",
        "collected_at": datetime.now().isoformat(),
        "count": len(signals),
        "signals": signals
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def save_to_file(signals: List[Dict[str, Any]], filename: str = None):
    """Save signals to JSON file."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"outputs/twitter_keywords_{timestamp}.json"
    
    Path("outputs").mkdir(exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "twitter",
            "source_type": "keyword-search", 
            "collected_at": datetime.now().isoformat(),
            "count": len(signals),
            "signals": signals
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Saved to: {filename}[/green]")
    return filename


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description='Twitter/X Keyword Search - Collect tweets from sources.json keywords'
    )
    parser.add_argument('--keywords', type=str, default=None,
                       help='Comma-separated keywords (overrides sources.json)')
    parser.add_argument('--limit', type=int, default=100,
                       help='Max tweets per keyword (default: 100)')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON to stdout')
    parser.add_argument('--save', action='store_true',
                       help='Save to file in outputs/')
    
    args = parser.parse_args()
    
    # Load keywords
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(',')]
    else:
        sources = load_sources()
        keywords = sources.get("keywords", [])
    
    if not keywords:
        console.print("[red]Error: No keywords found[/red]")
        sys.exit(1)
    
    # Check API key
    if not TWITTER_BEARER_TOKEN:
        console.print("[red]Error: TWITTER_BEARER_TOKEN not set in .env[/red]")
        console.print("[yellow]Get your bearer token at: https://developer.x.com/[/yellow]")
        sys.exit(1)
    
    # Collect signals
    signals = await collect_twitter_keywords(
        keywords=keywords,
        limit_per_keyword=args.limit
    )
    
    # Output
    if args.json:
        output_json(signals)
    else:
        print_summary(signals)
        
        if args.save:
            save_to_file(signals)


if __name__ == "__main__":
    asyncio.run(main())


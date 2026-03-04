#!/usr/bin/env python3
"""
Reddit Keyword Search Script

Searches Reddit posts based on keywords from sources.json.
Uses PRAW (Python Reddit API Wrapper).

Usage:
    python scripts/reddit_keyword_search.py                    # Search all keywords
    python scripts/reddit_keyword_search.py --keywords "AI marketing,growth"
    python scripts/reddit_keyword_search.py --subreddits "marketing,startups"
    python scripts/reddit_keyword_search.py --limit 50         # Limit per keyword
    python scripts/reddit_keyword_search.py --days 7           # Lookback days
    python scripts/reddit_keyword_search.py --json             # Output JSON to stdout
    python scripts/reddit_keyword_search.py --save             # Save to file
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import praw
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()

console = Console()

# Configuration
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "SignalCollection/1.0")
SOURCES_FILE = "sources.json"

# Default subreddits for marketing/business signals
DEFAULT_SUBREDDITS = [
    "marketing",
    "digital_marketing", 
    "startups",
    "Entrepreneur",
    "smallbusiness",
    "SaaS",
    "socialmedia",
    "content_marketing",
    "SEO",
    "artificial",
]


def load_sources() -> Dict[str, Any]:
    """Load sources.json configuration."""
    sources_path = Path(__file__).parent.parent / SOURCES_FILE
    
    if not sources_path.exists():
        console.print(f"[red]Error: {SOURCES_FILE} not found[/red]")
        sys.exit(1)
    
    with open(sources_path, 'r') as f:
        return json.load(f)


def get_reddit_client() -> praw.Reddit:
    """Initialize and return Reddit API client."""
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        console.print("[red]Error: Reddit API credentials not configured[/red]")
        console.print("[yellow]Set in .env file:[/yellow]")
        console.print("  REDDIT_CLIENT_ID=your_client_id")
        console.print("  REDDIT_CLIENT_SECRET=your_client_secret")
        sys.exit(1)
    
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def search_subreddit_keyword(
    reddit: praw.Reddit,
    subreddit_name: str,
    keyword: str,
    limit: int = 50,
    lookback_days: int = 7,
    seen_ids: Set[str] = None
) -> List[Dict[str, Any]]:
    """Search a subreddit for posts matching a keyword."""
    
    if seen_ids is None:
        seen_ids = set()
    
    cutoff_date = datetime.now() - timedelta(days=lookback_days)
    results = []
    
    # Determine time_filter based on lookback days
    if lookback_days <= 1:
        time_filter = "day"
    elif lookback_days <= 7:
        time_filter = "week"
    elif lookback_days <= 30:
        time_filter = "month"
    elif lookback_days <= 365:
        time_filter = "year"
    else:
        time_filter = "all"
    
    try:
        subreddit = reddit.subreddit(subreddit_name)
        
        for submission in subreddit.search(
            keyword,
            limit=limit * 2,  # Get extra to account for filtering
            time_filter=time_filter,
            sort="relevance"
        ):
            # Check date
            post_date = datetime.fromtimestamp(submission.created_utc)
            if post_date < cutoff_date:
                continue
            
            # Skip duplicates
            if submission.id in seen_ids:
                continue
            
            seen_ids.add(submission.id)
            
            results.append({
                "id": submission.id,
                "subreddit": subreddit_name,
                "title": submission.title,
                "selftext": submission.selftext[:2000] if submission.selftext else "",
                "url": submission.url,
                "permalink": f"https://reddit.com{submission.permalink}",
                "author": str(submission.author) if submission.author else "[deleted]",
                "created_utc": submission.created_utc,
                "score": submission.score,
                "upvote_ratio": submission.upvote_ratio,
                "num_comments": submission.num_comments,
                "is_self": submission.is_self,
            })
            
            if len(results) >= limit:
                break
    
    except Exception as e:
        console.print(f"[red]Error searching r/{subreddit_name}: {e}[/red]")
    
    return results


def transform_to_signal(post: Dict[str, Any], keyword: str) -> Dict[str, Any]:
    """Transform a Reddit post to signal format."""
    
    # Calculate engagement score
    engagement_total = post["score"] + post["num_comments"]
    
    return {
        "id": post["id"],
        "type": "reddit-keyword",
        "subreddit": f"r/{post['subreddit']}",
        "author": post["author"],
        "title": post["title"][:100] if post["title"] else "",
        "content": post["selftext"] if post["selftext"] else post["title"],
        "date_posted": datetime.fromtimestamp(post["created_utc"]).isoformat(),
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "url": post["permalink"],
        "external_url": post["url"] if not post["is_self"] else None,
        "matched_keyword": keyword,
        "engagement": {
            "score": post["score"],
            "upvote_ratio": post["upvote_ratio"],
            "comments": post["num_comments"],
            "total": engagement_total
        },
        "status": "unused",
    }


def collect_reddit_keywords(
    keywords: List[str],
    subreddits: List[str],
    limit_per_keyword: int = 50,
    lookback_days: int = 7,
    max_total: int = None
) -> List[Dict[str, Any]]:
    """Collect Reddit posts for multiple keywords across subreddits.
    
    Args:
        keywords: List of search keywords.
        subreddits: List of subreddit names to search.
        limit_per_keyword: Max posts per keyword (across all subreddits).
        lookback_days: How many days back to search.
        max_total: Overall cap on total signals returned. If set, collection
                   stops early once this many signals are gathered.
    """
    
    reddit = get_reddit_client()
    all_signals = []
    seen_ids: Set[str] = set()
    
    # If max_total is set, adjust per-keyword limit so we don't overshoot
    effective_per_kw = limit_per_keyword
    if max_total:
        effective_per_kw = min(limit_per_keyword, max(3, max_total // max(len(keywords), 1)))
    
    # Calculate per-subreddit limit from the effective per-keyword limit
    posts_per_sub = max(1, effective_per_kw // max(len(subreddits), 1))
    
    console.print(Panel(
        f'[bold cyan]Reddit Keyword Search[/bold cyan]\n\n'
        f'Keywords: {len(keywords)}\n'
        f'Subreddits: {len(subreddits)}\n'
        f'Limit per keyword: {effective_per_kw} ({posts_per_sub}/sub)\n'
        f'Total cap: {max_total or "none"}\n'
        f'Lookback: {lookback_days} days',
        border_style='cyan'
    ))
    
    # Show subreddits being searched
    console.print("\n[bold]Subreddits:[/bold]")
    console.print(f"  {', '.join([f'r/{s}' for s in subreddits[:10]])}")
    if len(subreddits) > 10:
        console.print(f"  ... and {len(subreddits) - 10} more")
    console.print()
    
    for i, keyword in enumerate(keywords, 1):
        # Check total cap before starting a new keyword
        if max_total and len(all_signals) >= max_total:
            console.print(f"[dim]   Reached total cap ({max_total}), skipping remaining keywords[/dim]")
            break
        
        console.print(f"[yellow][{i}/{len(keywords)}] Searching: \"{keyword}\"[/yellow]")
        
        keyword_signals = []
        keyword_budget = effective_per_kw
        if max_total:
            keyword_budget = min(effective_per_kw, max_total - len(all_signals))
        
        for subreddit in subreddits:
            if len(keyword_signals) >= keyword_budget:
                break
            
            sub_budget = min(posts_per_sub, keyword_budget - len(keyword_signals))
            if sub_budget <= 0:
                break
            
            posts = search_subreddit_keyword(
                reddit,
                subreddit,
                keyword,
                limit=sub_budget,
                lookback_days=lookback_days,
                seen_ids=seen_ids
            )
            
            for post in posts:
                if len(keyword_signals) >= keyword_budget:
                    break
                signal = transform_to_signal(post, keyword)
                keyword_signals.append(signal)
        
        all_signals.extend(keyword_signals)
        console.print(f"   [green]✓ Found {len(keyword_signals)} posts[/green]")
    
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
        console.print("[yellow]No posts found for the specified keywords.[/yellow]")
        return
    
    # Group by keyword
    by_keyword = {}
    for s in signals:
        kw = s.get("matched_keyword", "unknown")
        by_keyword[kw] = by_keyword.get(kw, 0) + 1
    
    table = Table(title="Posts by Keyword", show_header=True, header_style="bold magenta")
    table.add_column("Keyword", width=30)
    table.add_column("Count", width=10, justify="center")
    
    for kw, count in sorted(by_keyword.items(), key=lambda x: x[1], reverse=True):
        table.add_row(kw, str(count))
    
    console.print(table)
    
    # Group by subreddit
    by_subreddit = {}
    for s in signals:
        sub = s.get("subreddit", "unknown")
        by_subreddit[sub] = by_subreddit.get(sub, 0) + 1
    
    console.print()
    table2 = Table(title="Posts by Subreddit", show_header=True, header_style="bold magenta")
    table2.add_column("Subreddit", width=25)
    table2.add_column("Count", width=10, justify="center")
    
    for sub, count in sorted(by_subreddit.items(), key=lambda x: x[1], reverse=True)[:10]:
        table2.add_row(sub, str(count))
    
    console.print(table2)
    
    # Show top posts by engagement
    console.print("\n[bold]Top Posts by Engagement:[/bold]\n")
    
    sorted_signals = sorted(
        signals, 
        key=lambda x: x['engagement']['total'],
        reverse=True
    )
    
    for i, s in enumerate(sorted_signals[:5], 1):
        engagement = s['engagement']
        console.print(f"[magenta]{i}. {s['subreddit']}[/magenta] by u/{s['author']}")
        console.print(f"   ⬆️ {engagement['score']} | 💬 {engagement['comments']}")
        console.print(f"   {s['title'][:70]}...")
        console.print(f"   [cyan]🔗 {s['url']}[/cyan]")
        console.print()


def output_json(signals: List[Dict[str, Any]]):
    """Output signals as JSON to stdout."""
    output = {
        "platform": "reddit",
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
        filename = f"outputs/reddit_keywords_{timestamp}.json"
    
    Path("outputs").mkdir(exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "reddit",
            "source_type": "keyword-search", 
            "collected_at": datetime.now().isoformat(),
            "count": len(signals),
            "signals": signals
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Saved to: {filename}[/green]")
    return filename


def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description='Reddit Keyword Search - Collect posts from sources.json keywords'
    )
    parser.add_argument('--keywords', type=str, default=None,
                       help='Comma-separated keywords (overrides sources.json)')
    parser.add_argument('--subreddits', type=str, default=None,
                       help='Comma-separated subreddits to search (default: marketing/business subs)')
    parser.add_argument('--limit', type=int, default=50,
                       help='Max posts per keyword (default: 50)')
    parser.add_argument('--days', type=int, default=7,
                       help='Lookback days (default: 7)')
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
    
    # Load subreddits
    if args.subreddits:
        subreddits = [s.strip() for s in args.subreddits.split(',')]
    else:
        # Check if sources.json has subreddits, otherwise use defaults
        sources = load_sources()
        subreddits = sources.get("reddit-subreddits", DEFAULT_SUBREDDITS)
    
    # Collect signals
    signals = collect_reddit_keywords(
        keywords=keywords,
        subreddits=subreddits,
        limit_per_keyword=args.limit,
        lookback_days=args.days
    )
    
    # Output
    if args.json:
        output_json(signals)
    else:
        print_summary(signals)
        
        if args.save:
            save_to_file(signals)


if __name__ == "__main__":
    main()


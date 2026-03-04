#!/usr/bin/env python3
"""
LinkedIn Thought Leader Scraper

Scrapes recent posts from LinkedIn thought leaders defined in sources.json.
Uses Crustdata API keyword search with MEMBER filter.

Usage:
    python scripts/linkedin_thought_leaders.py                    # Scrape all thought leaders
    python scripts/linkedin_thought_leaders.py --days 14          # Past 14 days
    python scripts/linkedin_thought_leaders.py --limit 20         # 20 posts per person
    python scripts/linkedin_thought_leaders.py --json             # Output JSON to stdout
    python scripts/linkedin_thought_leaders.py --save             # Save to file
"""

import sys
import os
import json
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

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
CRUSTDATA_API_KEY = os.environ.get("CRUSTDATA_API_KEY", "")
CRUSTDATA_API_URL = "https://api.crustdata.com/screener/linkedin_posts/keyword_search/"
SOURCES_FILE = "sources.json"


def load_sources() -> Dict[str, Any]:
    """Load sources.json configuration."""
    sources_path = Path(__file__).parent.parent / SOURCES_FILE
    
    if not sources_path.exists():
        console.print(f"[red]Error: {SOURCES_FILE} not found[/red]")
        sys.exit(1)
    
    with open(sources_path, 'r') as f:
        return json.load(f)


def normalize_linkedin_url(url: str) -> str:
    """Normalize LinkedIn URL to proper format."""
    # Ensure URL starts with https://www.linkedin.com/
    url = url.strip()
    if not url.startswith("https://"):
        if url.startswith("www."):
            url = "https://" + url
        elif url.startswith("linkedin.com"):
            url = "https://www." + url
        else:
            url = "https://www.linkedin.com/in/" + url
    elif url.startswith("https://linkedin.com"):
        url = url.replace("https://linkedin.com", "https://www.linkedin.com")
    
    # Ensure trailing slash
    if not url.endswith("/"):
        url = url + "/"
    
    return url


async def fetch_thought_leader_posts(
    profile_urls: List[str],
    limit: int = 100,
    lookback_days: int = 7
) -> List[Dict[str, Any]]:
    """Fetch posts from thought leaders using MEMBER filter."""
    
    if not CRUSTDATA_API_KEY:
        console.print("[red]Error: CRUSTDATA_API_KEY not configured[/red]")
        return []
    
    # Normalize URLs
    normalized_urls = [normalize_linkedin_url(url) for url in profile_urls]
    
    headers = {
        "Authorization": f"Token {CRUSTDATA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Convert days to date_posted format
    if lookback_days <= 1:
        date_posted = "past-24h"
    elif lookback_days <= 7:
        date_posted = "past-week"
    elif lookback_days <= 30:
        date_posted = "past-month"
    elif lookback_days <= 90:
        date_posted = "past-quarter"
    else:
        date_posted = "past-year"
    
    # Use keyword search with MEMBER filter
    payload = {
        "keyword": "*",  # Wildcard to get all posts
        "limit": limit,
        "date_posted": date_posted,
        "sort_by": "date_posted",
        "filters": [
            {
                "filter_type": "MEMBER",
                "type": "in",
                "value": normalized_urls
            }
        ]
    }
    
    console.print(f"[cyan]Searching posts from {len(normalized_urls)} profiles...[/cyan]")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                CRUSTDATA_API_URL,
                headers=headers,
                json=payload,
                timeout=120.0
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle various response formats
                if isinstance(data, list):
                    posts = data
                elif isinstance(data, dict):
                    posts = data.get("posts", [])
                else:
                    posts = []
                
                console.print(f"[green]✓ API returned {len(posts)} posts[/green]")
                return posts
            
            elif response.status_code == 404:
                # API returns 404 when no posts found
                try:
                    error_data = response.json()
                    if "total_fetched_posts" in error_data:
                        console.print(f"[yellow]⚠️ No posts found (scanned: {error_data['total_fetched_posts']})[/yellow]")
                except:
                    console.print(f"[yellow]⚠️ No posts found[/yellow]")
                return []
            
            elif response.status_code == 429:
                console.print(f"[yellow]⚠️ Rate limited[/yellow]")
                return []
            
            else:
                console.print(f"[red]Error {response.status_code}: {response.text[:300]}[/red]")
                return []
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return []


def transform_to_signal(post: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a LinkedIn post to signal format."""
    
    actor_name = post.get("actor_name", "Unknown")
    text = post.get("text", "")
    share_url = post.get("share_url", "")
    date_posted = post.get("date_posted", "")
    reactions = post.get("total_reactions", 0)
    comments = post.get("total_comments", 0)
    num_shares = post.get("num_shares", 0)
    followers = post.get("actor_followers_count", 0)
    
    # Get person details if available
    person_details = post.get("person_details", {})
    title = person_details.get("title", "")
    company = person_details.get("company_name", "")
    location = person_details.get("location", "")
    
    return {
        "id": post.get("uid") or post.get("backend_urn", ""),
        "type": "linkedin-thought-leader",
        "author": actor_name,
        "author_title": title,
        "author_company": company,
        "author_location": location,
        "author_followers": followers,
        "title": text[:100] if text else "",
        "content": text,
        "date_posted": date_posted,
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "url": share_url,
        "engagement": {
            "reactions": reactions,
            "comments": comments,
            "shares": num_shares,
            "total": reactions + comments + num_shares
        },
        "status": "unused",
    }


async def collect_thought_leader_posts(
    profile_urls: List[str],
    limit: int = 100,
    lookback_days: int = 7
) -> List[Dict[str, Any]]:
    """Collect posts from thought leaders."""
    
    console.print(Panel(
        f'[bold cyan]LinkedIn Thought Leader Scraper[/bold cyan]\n\n'
        f'Profiles: {len(profile_urls)}\n'
        f'Max posts: {limit}\n'
        f'Lookback: {lookback_days} days',
        border_style='cyan'
    ))
    
    # Show profiles being scraped
    console.print("\n[bold]Profiles:[/bold]")
    for url in profile_urls:
        profile_id = url.split("/in/")[-1].strip("/")
        console.print(f"  • {profile_id}")
    console.print()
    
    # Fetch all posts in one API call
    posts = await fetch_thought_leader_posts(profile_urls, limit, lookback_days)
    
    # Transform to signals
    signals = []
    seen_urls = set()
    
    for post in posts:
        signal = transform_to_signal(post)
        
        # Deduplicate by URL
        if signal["url"] and signal["url"] not in seen_urls:
            seen_urls.add(signal["url"])
            signals.append(signal)
    
    return signals


def print_summary(signals: List[Dict[str, Any]]):
    """Print collection summary."""
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ COLLECTION COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Signals: [bold]{len(signals)}[/bold]\n")
    
    if not signals:
        console.print("[yellow]No posts found from these profiles in the specified time range.[/yellow]")
        return
    
    # Group by author
    by_author = {}
    for s in signals:
        author = s.get("author", "unknown")
        by_author[author] = by_author.get(author, 0) + 1
    
    table = Table(title="Posts by Thought Leader", show_header=True, header_style="bold magenta")
    table.add_column("Author", width=30)
    table.add_column("Posts", width=10, justify="center")
    
    for author, count in sorted(by_author.items(), key=lambda x: x[1], reverse=True):
        table.add_row(author[:30], str(count))
    
    console.print(table)
    
    # Show top posts by engagement
    console.print("\n[bold]Top Posts by Engagement:[/bold]\n")
    
    sorted_signals = sorted(
        signals, 
        key=lambda x: x['engagement']['total'],
        reverse=True
    )
    
    for i, s in enumerate(sorted_signals[:5], 1):
        engagement = s['engagement']['total']
        console.print(f"[magenta]{i}. {s['author']}[/magenta] ({engagement} engagements)")
        console.print(f"   {s['title'][:70]}...")
        if s['url']:
            console.print(f"   [cyan]🔗 {s['url'][:80]}[/cyan]")
        console.print()


def output_json(signals: List[Dict[str, Any]]):
    """Output signals as JSON to stdout."""
    output = {
        "platform": "linkedin",
        "source_type": "thought-leaders",
        "collected_at": datetime.now().isoformat(),
        "count": len(signals),
        "signals": signals
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def save_to_file(signals: List[Dict[str, Any]], filename: str = None):
    """Save signals to JSON file."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"outputs/linkedin_thought_leaders_{timestamp}.json"
    
    Path("outputs").mkdir(exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "linkedin",
            "source_type": "thought-leaders", 
            "collected_at": datetime.now().isoformat(),
            "count": len(signals),
            "signals": signals
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Saved to: {filename}[/green]")
    return filename


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description='LinkedIn Thought Leader Scraper - Collect posts from thought leaders in sources.json'
    )
    parser.add_argument('--profiles', type=str, default=None,
                       help='Comma-separated LinkedIn profile URLs (overrides sources.json)')
    parser.add_argument('--limit', type=int, default=100,
                       help='Max posts total (default: 100)')
    parser.add_argument('--days', type=int, default=7,
                       help='Lookback days (default: 7)')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON to stdout')
    parser.add_argument('--save', action='store_true',
                       help='Save to file in outputs/')
    
    args = parser.parse_args()
    
    # Load profile URLs
    if args.profiles:
        profile_urls = [p.strip() for p in args.profiles.split(',')]
    else:
        sources = load_sources()
        profile_urls = sources.get("linkedin-thought-leaders", [])
    
    if not profile_urls:
        console.print("[red]Error: No LinkedIn profiles found[/red]")
        sys.exit(1)
    
    # Check API key
    if not CRUSTDATA_API_KEY:
        console.print("[red]Error: CRUSTDATA_API_KEY not set in .env[/red]")
        sys.exit(1)
    
    # Collect posts
    signals = await collect_thought_leader_posts(
        profile_urls=profile_urls,
        limit=args.limit,
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
    asyncio.run(main())

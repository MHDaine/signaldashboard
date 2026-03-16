#!/usr/bin/env python3
"""
LinkedIn Keyword Search Script

Scrapes LinkedIn posts based on keywords defined in sources.json.
Uses Crustdata API for data collection.

Usage:
    python scripts/linkedin_keyword_search.py                    # Collect all keywords
    python scripts/linkedin_keyword_search.py --keywords "AI marketing,fractional CMO"
    python scripts/linkedin_keyword_search.py --limit 50         # Limit per keyword
    python scripts/linkedin_keyword_search.py --json             # Output JSON to stdout
"""

import sys
import os
import json
import argparse
import asyncio
from datetime import datetime
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


async def search_linkedin_keyword(
    keyword: str,
    limit: int = 50,
    lookback_days: int = 7
) -> List[Dict[str, Any]]:
    """Search LinkedIn for posts matching a keyword."""
    
    if not CRUSTDATA_API_KEY:
        console.print("[red]Error: CRUSTDATA_API_KEY not configured[/red]")
        return []
    
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
    else:
        date_posted = "past-month"
    
    payload = {
        "keyword": keyword,
        "limit": limit,
        "date_posted": date_posted,
        "sort_by": "relevance",
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                CRUSTDATA_API_URL,
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle both list and dict responses
                if isinstance(data, list):
                    posts = data
                else:
                    posts = data.get("posts", [])
                
                return posts
            
            elif response.status_code == 429:
                console.print(f"[yellow]⚠️ Rate limited for '{keyword}'[/yellow]")
                return []
            
            else:
                console.print(f"[red]Error {response.status_code} for '{keyword}': {response.text[:200]}[/red]")
                return []
    
    except Exception as e:
        console.print(f"[red]Error searching '{keyword}': {e}[/red]")
        return []


def transform_to_signal(post: Dict[str, Any], keyword: str) -> Dict[str, Any]:
    """Transform a LinkedIn post to signal format."""
    
    actor_name = post.get("actor_name", "Unknown")
    text = post.get("text", "")
    share_url = post.get("share_url", "")
    date_posted = post.get("date_posted", "")
    reactions = post.get("total_reactions", 0)
    comments = post.get("total_comments", 0)
    
    # Get person details if available
    person_details = post.get("person_details", {})
    title = person_details.get("title", "")
    company = person_details.get("company_name", "")
    
    return {
        "id": post.get("uid") or post.get("backend_urn", ""),
        "type": "linkedin-keyword",
        "author": actor_name,
        "author_title": title,
        "author_company": company,
        "title": text[:100] if text else "",
        "content": text,
        "date_posted": date_posted,
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "url": share_url,
        "matched_keyword": keyword,
        "engagement": {
            "reactions": reactions,
            "comments": comments,
        },
        "status": "unused",
    }


async def collect_linkedin_keywords(
    keywords: List[str],
    limit_per_keyword: int = 50,
    lookback_days: int = 7
) -> List[Dict[str, Any]]:
    """Collect LinkedIn posts for multiple keywords."""
    
    all_signals = []
    seen_urls = set()
    
    console.print(Panel(
        f'[bold cyan]LinkedIn Keyword Search[/bold cyan]\n\n'
        f'Keywords: {len(keywords)}\n'
        f'Limit per keyword: {limit_per_keyword}\n'
        f'Lookback: {lookback_days} days',
        border_style='cyan'
    ))
    
    for i, keyword in enumerate(keywords, 1):
        console.print(f"\n[yellow][{i}/{len(keywords)}] Searching: \"{keyword}\"[/yellow]")
        
        posts = await search_linkedin_keyword(keyword, limit_per_keyword, lookback_days)
        
        new_count = 0
        for post in posts:
            signal = transform_to_signal(post, keyword)
            
            # Deduplicate by URL
            if signal["url"] and signal["url"] not in seen_urls:
                seen_urls.add(signal["url"])
                all_signals.append(signal)
                new_count += 1
        
        console.print(f"   [green]✓ Found {len(posts)} posts, {new_count} new[/green]")
        
        # Small delay between requests
        await asyncio.sleep(1)
    
    return all_signals


def print_summary(signals: List[Dict[str, Any]]):
    """Print collection summary."""
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ COLLECTION COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Signals: [bold]{len(signals)}[/bold]\n")
    
    # Group by keyword
    by_keyword = {}
    for s in signals:
        kw = s.get("matched_keyword", "unknown")
        by_keyword[kw] = by_keyword.get(kw, 0) + 1
    
    table = Table(title="Signals by Keyword", show_header=True, header_style="bold magenta")
    table.add_column("Keyword", width=30)
    table.add_column("Count", width=10, justify="center")
    
    for kw, count in sorted(by_keyword.items(), key=lambda x: x[1], reverse=True):
        table.add_row(kw, str(count))
    
    console.print(table)
    
    # Show sample signals
    console.print("\n[bold]Sample Signals:[/bold]\n")
    
    for i, s in enumerate(signals[:5], 1):
        console.print(f"[magenta]{i}. {s['author']}[/magenta]")
        console.print(f"   {s['title'][:70]}...")
        if s['url']:
            console.print(f"   [cyan]🔗 {s['url']}[/cyan]")
        console.print()


def output_json(signals: List[Dict[str, Any]]):
    """Output signals as JSON to stdout."""
    output = {
        "platform": "linkedin",
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
        filename = f"outputs/linkedin_keywords_{timestamp}.json"
    
    Path("outputs").mkdir(exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "linkedin",
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
        description='LinkedIn Keyword Search - Collect posts from sources.json keywords'
    )
    parser.add_argument('--keywords', type=str, default=None,
                       help='Comma-separated keywords (overrides sources.json)')
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
    
    # Check API key
    if not CRUSTDATA_API_KEY:
        console.print("[red]Error: CRUSTDATA_API_KEY not set in .env[/red]")
        sys.exit(1)
    
    # Collect signals
    signals = await collect_linkedin_keywords(
        keywords=keywords,
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
    asyncio.run(main())


#!/usr/bin/env python3
"""
RSS Feed Scraper

Fetches posts from RSS feeds defined in sources.json.
Idempotent - tracks seen URLs to avoid duplicates.

Usage:
    python scripts/rss_feed_scraper.py                    # Fetch all feeds
    python scripts/rss_feed_scraper.py --feeds "url1,url2" # Custom feeds
    python scripts/rss_feed_scraper.py --limit 20         # Limit per feed
    python scripts/rss_feed_scraper.py --days 7           # Only posts from last 7 days
    python scripts/rss_feed_scraper.py --json             # Output JSON to stdout
    python scripts/rss_feed_scraper.py --save             # Save to file
"""

import sys
import os
import json
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse
import html

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import feedparser
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()

console = Console()

# Configuration
SOURCES_FILE = "sources.json"


def load_sources() -> Dict[str, Any]:
    """Load sources.json configuration."""
    sources_path = Path(__file__).parent.parent / SOURCES_FILE
    
    if not sources_path.exists():
        console.print(f"[red]Error: {SOURCES_FILE} not found[/red]")
        sys.exit(1)
    
    with open(sources_path, 'r') as f:
        return json.load(f)


def get_source_domain(feed_url: str) -> str:
    """Extract domain from feed URL."""
    parsed = urlparse(feed_url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def get_source_name(feed_url: str) -> str:
    """Extract a friendly source name from feed URL."""
    domain = get_source_domain(feed_url)
    # Remove common TLDs and clean up
    name = domain.split('.')[0]
    return name.title()


def parse_date(entry) -> Optional[datetime]:
    """Extract datetime from feed entry."""
    for attr in ["published_parsed", "updated_parsed", "created_parsed"]:
        if hasattr(entry, attr) and getattr(entry, attr):
            try:
                return datetime(*getattr(entry, attr)[:6])
            except (TypeError, ValueError):
                continue
    return None


def clean_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_content(entry) -> str:
    """Extract content from feed entry."""
    content = ""
    if hasattr(entry, "content") and entry.content:
        content = entry.content[0].value
    elif hasattr(entry, "summary"):
        content = entry.summary
    elif hasattr(entry, "description"):
        content = entry.description
    return clean_html(content)


def get_short_hash(url: str) -> str:
    """Generate short hash from URL for deduplication."""
    return hashlib.sha256(url.encode()).hexdigest()[:8]


def fetch_feed(feed_url: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch and parse RSS feed."""
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            console.print(f"[yellow]⚠️ Error parsing feed: {feed.bozo_exception}[/yellow]")
            return []
        return feed.entries[:limit]
    except Exception as e:
        console.print(f"[red]Error fetching feed: {e}[/red]")
        return []


def transform_to_signal(
    entry: Dict[str, Any],
    feed_url: str,
    source_name: str
) -> Dict[str, Any]:
    """Transform an RSS entry to signal format."""
    
    url = entry.get("link", "")
    title = entry.get("title", "Untitled")
    content = get_content(entry)
    
    # Get author - try multiple fields
    author = source_name
    if hasattr(entry, "author") and entry.author:
        author = entry.author
    elif hasattr(entry, "author_detail") and entry.author_detail:
        author = entry.author_detail.get("name", source_name)
    
    # Parse date
    post_date = parse_date(entry)
    date_posted = post_date.isoformat() if post_date else datetime.now().isoformat()
    
    # Get tags/categories if available
    tags = []
    if hasattr(entry, "tags") and entry.tags:
        tags = [tag.term for tag in entry.tags[:5]]
    
    return {
        "id": get_short_hash(url),
        "type": "rss-feed",
        "source": source_name,
        "source_url": feed_url,
        "author": clean_html(author),
        "title": clean_html(title)[:200],
        "content": content[:2000] if content else clean_html(title),
        "date_posted": date_posted,
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "url": url,
        "tags": tags,
        "engagement": {
            "comments": 0,  # RSS doesn't typically include this
            "shares": 0,
        },
        "status": "unused",
    }


def collect_rss_feeds(
    feed_urls: List[str],
    limit_per_feed: int = 50,
    lookback_days: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Collect posts from multiple RSS feeds."""
    
    all_signals = []
    seen_urls: Set[str] = set()
    cutoff_date = None
    
    if lookback_days:
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
    
    console.print(Panel(
        f'[bold cyan]RSS Feed Scraper[/bold cyan]\n\n'
        f'Feeds: {len(feed_urls)}\n'
        f'Limit per feed: {limit_per_feed}\n'
        f'Lookback: {f"{lookback_days} days" if lookback_days else "All available"}',
        border_style='cyan'
    ))
    
    for i, feed_url in enumerate(feed_urls, 1):
        source_name = get_source_name(feed_url)
        console.print(f"\n[yellow][{i}/{len(feed_urls)}] Fetching: {source_name}[/yellow]")
        console.print(f"   [dim]{feed_url}[/dim]")
        
        entries = fetch_feed(feed_url, limit_per_feed)
        
        feed_signals = []
        for entry in entries:
            url = entry.get("link", "")
            
            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            # Check date if lookback specified
            if cutoff_date:
                post_date = parse_date(entry)
                if post_date and post_date < cutoff_date:
                    continue
            
            signal = transform_to_signal(entry, feed_url, source_name)
            feed_signals.append(signal)
        
        all_signals.extend(feed_signals)
        console.print(f"   [green]✓ Found {len(feed_signals)} posts[/green]")
    
    return all_signals


def print_summary(signals: List[Dict[str, Any]]):
    """Print collection summary."""
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ COLLECTION COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Signals: [bold]{len(signals)}[/bold]\n")
    
    if not signals:
        console.print("[yellow]No posts found from the RSS feeds.[/yellow]")
        return
    
    # Group by source
    by_source = {}
    for s in signals:
        source = s.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + 1
    
    table = Table(title="Posts by Source", show_header=True, header_style="bold magenta")
    table.add_column("Source", width=30)
    table.add_column("Count", width=10, justify="center")
    
    for source, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True):
        table.add_row(source, str(count))
    
    console.print(table)
    
    # Show recent posts
    console.print("\n[bold]Recent Posts:[/bold]\n")
    
    # Sort by date
    sorted_signals = sorted(
        signals, 
        key=lambda x: x.get('date_posted', ''),
        reverse=True
    )
    
    for i, s in enumerate(sorted_signals[:5], 1):
        console.print(f"[magenta]{i}. {s['source']}[/magenta] - {s['author']}")
        console.print(f"   {s['title'][:70]}...")
        if s.get('tags'):
            console.print(f"   [dim]Tags: {', '.join(s['tags'][:3])}[/dim]")
        console.print(f"   [cyan]🔗 {s['url'][:80]}[/cyan]")
        console.print()


def output_json(signals: List[Dict[str, Any]]):
    """Output signals as JSON to stdout."""
    output = {
        "platform": "rss",
        "source_type": "rss-feeds",
        "collected_at": datetime.now().isoformat(),
        "count": len(signals),
        "signals": signals
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def save_to_file(signals: List[Dict[str, Any]], filename: str = None):
    """Save signals to JSON file."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"outputs/rss_feeds_{timestamp}.json"
    
    Path("outputs").mkdir(exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "rss",
            "source_type": "rss-feeds", 
            "collected_at": datetime.now().isoformat(),
            "count": len(signals),
            "signals": signals
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Saved to: {filename}[/green]")
    return filename


def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description='RSS Feed Scraper - Collect posts from RSS feeds in sources.json'
    )
    parser.add_argument('--feeds', type=str, default=None,
                       help='Comma-separated feed URLs (overrides sources.json)')
    parser.add_argument('--limit', type=int, default=50,
                       help='Max posts per feed (default: 50)')
    parser.add_argument('--days', type=int, default=None,
                       help='Only include posts from last N days (default: all)')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON to stdout')
    parser.add_argument('--save', action='store_true',
                       help='Save to file in outputs/')
    
    args = parser.parse_args()
    
    # Load feed URLs
    if args.feeds:
        feed_urls = [f.strip() for f in args.feeds.split(',')]
    else:
        sources = load_sources()
        feed_urls = sources.get("web-sources-rss", [])
    
    if not feed_urls:
        console.print("[red]Error: No RSS feeds found[/red]")
        console.print("[yellow]Add feeds to sources.json under 'web-sources-rss'[/yellow]")
        sys.exit(1)
    
    # Collect signals
    signals = collect_rss_feeds(
        feed_urls=feed_urls,
        limit_per_feed=args.limit,
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


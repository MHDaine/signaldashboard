#!/usr/bin/env python3
"""
Collect All Signals - Main Orchestrator Script

Runs all signal collection scripts in parallel and aggregates results.
Uses sources.json for configuration and context_summary.md for Perplexity queries.

Sources:
- LinkedIn Keyword Search (Crustdata API)
- LinkedIn Thought Leaders (Crustdata API)
- Twitter/X Keyword Search (X API v2)
- Reddit Keyword Search (PRAW)
- RSS Feeds (feedparser)
- Perplexity News Search (Perplexity Agent API)

Usage:
    python scripts/collect_all_signals.py                    # Collect from all sources
    python scripts/collect_all_signals.py --sources linkedin,twitter,reddit
    python scripts/collect_all_signals.py --limit 50         # Limit per source
    python scripts/collect_all_signals.py --days 7           # Lookback days
    python scripts/collect_all_signals.py --json             # Output JSON to stdout
    python scripts/collect_all_signals.py --save             # Save to file
"""

import sys
import os
import json
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.live import Live

load_dotenv()

console = Console(stderr=True)  # rich output to stderr, keep stdout clean for PROGRESS lines

# Import collection functions from individual scripts
from scripts.linkedin_keyword_search import collect_linkedin_keywords, CRUSTDATA_API_KEY
from scripts.linkedin_thought_leaders import collect_thought_leader_posts
from scripts.twitter_keyword_search import collect_twitter_keywords, TWITTER_BEARER_TOKEN
from scripts.reddit_keyword_search import collect_reddit_keywords, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
from scripts.rss_feed_scraper import collect_rss_feeds
from scripts.perplexity_news_search import (
    collect_perplexity_news, 
    generate_news_queries, 
    load_context_summary,
    PERPLEXITY_API_KEY
)

def emit_progress(
    completed_sources: int,
    total_sources: int,
    source_results: Dict[str, Any],
    status: str = "running"
):
    """Emit collection progress as a JSON line to stdout so the frontend can read it.
    
    Uses os.write(1, ...) to bypass any stdout interception (e.g. by rich).
    """
    try:
        total_signals = sum(
            r.get("count", 0) for r in source_results.values()
        )
        line = "PROGRESS:" + json.dumps({
            "completed_sources": completed_sources,
            "total_sources": total_sources,
            "total_signals": total_signals,
            "source_results": {
                k: {"count": v.get("count", 0), "error": v.get("error")}
                for k, v in source_results.items()
            },
            "status": status,
        }) + "\n"
        os.write(1, line.encode())
    except Exception:
        pass  # Non-critical


# Configuration files
SOURCES_FILE = "sources.json"
CONTEXT_FILE = "context/context_summary.md"

# Available sources
ALL_SOURCES = [
    "linkedin-keywords",
    "linkedin-leaders",
    "twitter",
    "reddit",
    "rss",
    "perplexity"
]


def load_sources() -> Dict[str, Any]:
    """Load sources.json configuration."""
    sources_path = Path(__file__).parent.parent / SOURCES_FILE
    
    if not sources_path.exists():
        console.print(f"[red]Error: {SOURCES_FILE} not found[/red]")
        return {}
    
    with open(sources_path, 'r') as f:
        return json.load(f)


def check_api_availability() -> Dict[str, bool]:
    """Check which APIs are available based on configured keys."""
    return {
        "linkedin-keywords": bool(CRUSTDATA_API_KEY),
        "linkedin-leaders": bool(CRUSTDATA_API_KEY),
        "twitter": bool(TWITTER_BEARER_TOKEN),
        "reddit": bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET),
        "rss": True,  # No API key needed
        "perplexity": bool(PERPLEXITY_API_KEY),
    }


async def collect_linkedin_keyword_signals(
    keywords: List[str],
    limit: int,
    days: int
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Wrapper for LinkedIn keyword collection."""
    source_name = "linkedin-keywords"
    try:
        signals = await collect_linkedin_keywords(
            keywords=keywords,
            limit_per_keyword=limit,
            lookback_days=days
        )
        return source_name, signals, None
    except Exception as e:
        return source_name, [], str(e)


async def collect_linkedin_leader_signals(
    profile_urls: List[str],
    limit: int,
    days: int
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Wrapper for LinkedIn thought leader collection."""
    source_name = "linkedin-leaders"
    try:
        signals = await collect_thought_leader_posts(
            profile_urls=profile_urls,
            limit=limit,
            lookback_days=days
        )
        return source_name, signals, None
    except Exception as e:
        return source_name, [], str(e)


async def collect_twitter_signals(
    keywords: List[str],
    limit: int,
    days: int  # Note: Twitter API only searches last 7 days by default
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Wrapper for Twitter collection. Enforces total cap via max_total."""
    source_name = "twitter"
    try:
        signals = await collect_twitter_keywords(
            keywords=keywords,
            limit_per_keyword=limit,
            max_total=limit
        )
        return source_name, signals, None
    except Exception as e:
        return source_name, [], str(e)


async def collect_reddit_signals(
    keywords: List[str],
    subreddits: List[str],
    limit: int,
    days: int
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Wrapper for Reddit collection (sync function in async context). Enforces total cap via max_total."""
    source_name = "reddit"
    try:
        # Run sync function in thread pool
        loop = asyncio.get_event_loop()
        signals = await loop.run_in_executor(
            None,
            lambda: collect_reddit_keywords(
                keywords=keywords,
                subreddits=subreddits,
                limit_per_keyword=limit,
                lookback_days=days,
                max_total=limit
            )
        )
        return source_name, signals, None
    except Exception as e:
        return source_name, [], str(e)


async def collect_rss_signals(
    feed_urls: List[str],
    limit: int,
    days: int
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Wrapper for RSS collection (sync function in async context)."""
    source_name = "rss"
    try:
        # Run sync function in thread pool
        loop = asyncio.get_event_loop()
        signals = await loop.run_in_executor(
            None,
            lambda: collect_rss_feeds(
                feed_urls=feed_urls,
                limit_per_feed=limit,
                lookback_days=days
            )
        )
        return source_name, signals, None
    except Exception as e:
        return source_name, [], str(e)


async def collect_perplexity_signals(
    queries: List[str],
    days: int,
    limit_per_query: int = 50
) -> Tuple[str, List[Dict[str, Any]], Optional[str], List[Dict[str, Any]]]:
    """Wrapper for Perplexity collection. Capped at limit_per_query per query."""
    source_name = "perplexity"
    try:
        signals, content = await collect_perplexity_news(
            queries=queries,
            recency_days=days,
            limit_per_query=limit_per_query
        )
        return source_name, signals, None, content
    except Exception as e:
        return source_name, [], str(e), []


def deduplicate_signals(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate signals by URL."""
    seen_urls = set()
    unique_signals = []
    
    for signal in signals:
        url = signal.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_signals.append(signal)
        elif not url:
            # Keep signals without URLs (they can't be deduplicated)
            unique_signals.append(signal)
    
    return unique_signals


def get_engagement_score(signal: Dict[str, Any]) -> int:
    """
    Calculate total engagement score for a signal.
    Different platforms have different engagement metrics.
    """
    engagement = signal.get("engagement", {})
    source = signal.get("collection_source", "") or signal.get("type", "")
    
    # LinkedIn: reactions + comments
    if "linkedin" in source:
        return engagement.get("reactions", 0) + engagement.get("comments", 0)
    
    # Twitter: likes + retweets + replies
    elif "twitter" in source:
        return (
            engagement.get("likes", 0) + 
            engagement.get("retweets", 0) + 
            engagement.get("replies", 0)
        )
    
    # Reddit: score (upvotes - downvotes) + comments
    elif "reddit" in source:
        return engagement.get("score", 0) + engagement.get("comments", 0)
    
    # RSS/Perplexity: no engagement data, always pass
    else:
        return float('inf')  # Always pass filter


def filter_by_engagement(
    signals: List[Dict[str, Any]], 
    min_engagement: int
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Filter signals by minimum engagement score.
    Returns filtered signals and count of removed signals.
    """
    if min_engagement <= 0:
        return signals, 0
    
    filtered = []
    removed_count = 0
    
    for signal in signals:
        score = get_engagement_score(signal)
        if score >= min_engagement:
            filtered.append(signal)
        else:
            removed_count += 1
    
    return filtered, removed_count


async def collect_all_signals(
    sources_to_run: List[str],
    limit: int = 50,
    days: int = 7,
    min_engagement: int = 0
) -> Dict[str, Any]:
    """
    Run all signal collection in parallel.
    
    Returns aggregated results with metadata.
    """
    sources_config = load_sources()
    api_availability = check_api_availability()
    
    # Filter sources based on API availability
    available_sources = [s for s in sources_to_run if api_availability.get(s, False)]
    unavailable_sources = [s for s in sources_to_run if not api_availability.get(s, False)]
    
    if unavailable_sources:
        console.print(f"[yellow]⚠️ Skipping sources (missing API keys): {', '.join(unavailable_sources)}[/yellow]")
    
    # Load data from sources.json
    keywords = sources_config.get("keywords", [])
    linkedin_profiles = sources_config.get("linkedin-thought-leaders", [])
    subreddits = sources_config.get("reddit-subreddits", [])
    rss_feeds = sources_config.get("web-sources-rss", [])
    
    # Generate Perplexity queries from context
    context = load_context_summary()
    perplexity_queries = generate_news_queries(context)
    
    # Create tasks for parallel execution
    tasks = []
    source_tasks = {}
    
    engagement_info = f"\nMin Engagement: {min_engagement}" if min_engagement > 0 else ""
    console.print(Panel(
        f'[bold cyan]Signal Collection Pipeline[/bold cyan]\n\n'
        f'Sources: {", ".join(available_sources)}\n'
        f'Keywords: {len(keywords)}\n'
        f'Target: ~{limit} signals per source\n'
        f'Lookback: {days} days{engagement_info}',
        border_style='cyan'
    ))
    
    # Calculate per-keyword/per-item limits to normalize total signals per source
    # Goal: Each source returns roughly `limit` total signals
    # Twitter and Reddit now enforce max_total internally, so we pass `limit` as the source cap
    num_keywords = len(keywords) if keywords else 1
    num_linkedin_profiles = len(linkedin_profiles) if linkedin_profiles else 1
    num_rss_feeds = len(rss_feeds) if rss_feeds else 1
    
    linkedin_per_keyword = max(5, limit // num_keywords)
    rss_per_feed = max(5, limit // num_rss_feeds)
    linkedin_leaders_per_profile = max(5, limit // num_linkedin_profiles)
    
    if "linkedin-keywords" in available_sources and keywords:
        task = collect_linkedin_keyword_signals(keywords, linkedin_per_keyword, days)
        tasks.append(task)
        source_tasks["linkedin-keywords"] = len(tasks) - 1
    
    if "linkedin-leaders" in available_sources and linkedin_profiles:
        task = collect_linkedin_leader_signals(linkedin_profiles, linkedin_leaders_per_profile, days)
        tasks.append(task)
        source_tasks["linkedin-leaders"] = len(tasks) - 1
    
    if "twitter" in available_sources and keywords:
        task = collect_twitter_signals(keywords, limit, days)
        tasks.append(task)
        source_tasks["twitter"] = len(tasks) - 1
    
    if "reddit" in available_sources and keywords:
        task = collect_reddit_signals(keywords, subreddits, limit, days)
        tasks.append(task)
        source_tasks["reddit"] = len(tasks) - 1
    
    if "rss" in available_sources and rss_feeds:
        task = collect_rss_signals(rss_feeds, rss_per_feed, days)
        tasks.append(task)
        source_tasks["rss"] = len(tasks) - 1
    
    if "perplexity" in available_sources:
        task = collect_perplexity_signals(perplexity_queries, days, limit_per_query=50)
        tasks.append(task)
        source_tasks["perplexity"] = len(tasks) - 1
    
    if not tasks:
        console.print("[red]No sources to collect from![/red]")
        return {"signals": [], "metadata": {}}
    
    # Build a name list matching task indices
    task_names = []
    for src_name, idx in source_tasks.items():
        while len(task_names) <= idx:
            task_names.append("unknown")
        task_names[idx] = src_name
    
    total_sources = len(tasks)
    
    # Shared state for progress tracking across concurrent tasks
    all_signals = []
    source_results = {}
    perplexity_content = []
    completed_count = [0]  # mutable container for closure
    
    async def tracked_task(coro, src_name: str):
        """Wrapper that updates progress when each source completes."""
        try:
            result = await coro
        except Exception as e:
            console.print(f"[red]Error ({src_name}): {e}[/red]")
            source_results[src_name] = {"count": 0, "error": str(e)[:200]}
            completed_count[0] += 1
            emit_progress(completed_count[0], total_sources, source_results, "running")
            return
        
        # Handle Perplexity's extra return value
        if len(result) == 4:
            source_name, signals, error, content = result
            nonlocal perplexity_content
            perplexity_content = content
        else:
            source_name, signals, error = result
        
        if error:
            console.print(f"[red]✗ {source_name}: {error}[/red]")
            source_results[source_name] = {"count": 0, "error": error}
        else:
            console.print(f"[green]✓ {source_name}: {len(signals)} signals[/green]")
            source_results[source_name] = {"count": len(signals), "error": None}
            for signal in signals:
                signal["collection_source"] = source_name
            all_signals.extend(signals)
        
        completed_count[0] += 1
        emit_progress(completed_count[0], total_sources, source_results, "running")
    
    # Run all tasks in parallel
    console.print(f"\n[bold]🚀 Running {total_sources} collectors in parallel...[/bold]\n")
    
    # Emit initial progress
    emit_progress(0, total_sources, {}, "running")
    
    # Wrap each task with progress tracking and run concurrently
    wrapped_tasks = [
        tracked_task(task, task_names[i] if i < len(task_names) else f"source-{i}")
        for i, task in enumerate(tasks)
    ]
    await asyncio.gather(*wrapped_tasks, return_exceptions=True)
    
    # Deduplicate
    original_count = len(all_signals)
    all_signals = deduplicate_signals(all_signals)
    duplicates_removed = original_count - len(all_signals)
    
    if duplicates_removed > 0:
        console.print(f"\n[dim]Removed {duplicates_removed} duplicate signals[/dim]")
    
    # Filter by engagement
    low_engagement_removed = 0
    if min_engagement > 0:
        all_signals, low_engagement_removed = filter_by_engagement(all_signals, min_engagement)
        if low_engagement_removed > 0:
            console.print(f"[dim]Filtered {low_engagement_removed} low-engagement signals (min: {min_engagement})[/dim]")
    
    # Emit final progress
    emit_progress(total_sources, total_sources, source_results, "complete")
    
    return {
        "signals": all_signals,
        "metadata": {
            "collected_at": datetime.now().isoformat(),
            "sources_requested": sources_to_run,
            "sources_run": available_sources,
            "sources_skipped": unavailable_sources,
            "source_results": source_results,
            "total_signals": len(all_signals),
            "duplicates_removed": duplicates_removed,
            "low_engagement_removed": low_engagement_removed,
            "config": {
                "limit": limit,
                "lookback_days": days,
                "min_engagement": min_engagement,
                "keywords_count": len(keywords),
                "profiles_count": len(linkedin_profiles),
                "subreddits_count": len(subreddits),
                "rss_feeds_count": len(rss_feeds),
            }
        },
        "perplexity_summaries": perplexity_content
    }


def print_summary(result: Dict[str, Any]):
    """Print collection summary."""
    metadata = result.get("metadata", {})
    signals = result.get("signals", [])
    source_results = metadata.get("source_results", {})
    config = metadata.get("config", {})
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ COLLECTION COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Signals: [bold]{len(signals)}[/bold]")
    console.print(f"🗑️ Duplicates Removed: {metadata.get('duplicates_removed', 0)}")
    
    low_engagement = metadata.get('low_engagement_removed', 0)
    if low_engagement > 0:
        min_eng = config.get('min_engagement', 0)
        console.print(f"📉 Low Engagement Filtered: {low_engagement} (min: {min_eng})")
    console.print()
    
    # Source breakdown table
    table = Table(title="Collection Results by Source", show_header=True, header_style="bold magenta")
    table.add_column("Source", width=20)
    table.add_column("Signals", width=10, justify="right")
    table.add_column("Status", width=15)
    
    for source, data in source_results.items():
        count = data.get("count", 0)
        error = data.get("error")
        status = "[green]✓ Success[/green]" if not error else f"[red]✗ Error[/red]"
        table.add_row(source, str(count), status)
    
    console.print(table)
    
    # Sample signals
    if signals:
        console.print(f"\n[bold]Sample Signals:[/bold]\n")
        
        for i, signal in enumerate(signals[:8], 1):
            source = signal.get("collection_source", "unknown")
            title = signal.get("title", "No title")[:60]
            url = signal.get("url", "")[:70]
            
            console.print(f"[magenta]{i}. [{source}] {title}...[/magenta]")
            if url:
                console.print(f"   [cyan]🔗 {url}...[/cyan]")


def output_json(result: Dict[str, Any]):
    """Output results as JSON to stdout."""
    output = {
        "platform": "multi-source",
        "source_type": "aggregated-signals",
        **result
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


SIGNALS_FILE = "outputs/signals.json"


def save_to_file(result: Dict[str, Any], filename: str = None):
    """Save results to the single signals.json file."""
    filename = filename or SIGNALS_FILE
    
    Path("outputs").mkdir(exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "multi-source",
            "source_type": "aggregated-signals",
            **result
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Saved to: {filename}[/green]")
    return filename


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description='Collect All Signals - Run all signal collectors in parallel'
    )
    parser.add_argument('--sources', type=str, default=None,
                       help=f'Comma-separated sources to run. Options: {", ".join(ALL_SOURCES)} (default: all)')
    parser.add_argument('--limit', type=int, default=50,
                       help='Max signals per source/keyword (default: 50)')
    parser.add_argument('--days', type=int, default=7,
                       help='Lookback days (default: 7)')
    parser.add_argument('--min-engagement', type=int, default=0,
                       help='Minimum engagement score to include (default: 0 = no filter). '
                            'LinkedIn: reactions+comments, Twitter: likes+retweets+replies, Reddit: score+comments')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON to stdout')
    parser.add_argument('--save', action='store_true',
                       help='Save to file in outputs/')
    parser.add_argument('--list-sources', action='store_true',
                       help='List available sources and exit')
    
    args = parser.parse_args()
    
    # List sources and exit
    if args.list_sources:
        api_availability = check_api_availability()
        console.print("\n[bold]Available Signal Sources:[/bold]\n")
        for source in ALL_SOURCES:
            available = api_availability.get(source, False)
            status = "[green]✓ Ready[/green]" if available else "[red]✗ Missing API Key[/red]"
            console.print(f"  • {source}: {status}")
        return
    
    # Parse sources
    if args.sources:
        sources_to_run = [s.strip() for s in args.sources.split(',')]
        invalid_sources = [s for s in sources_to_run if s not in ALL_SOURCES]
        if invalid_sources:
            console.print(f"[red]Invalid sources: {', '.join(invalid_sources)}[/red]")
            console.print(f"[yellow]Valid options: {', '.join(ALL_SOURCES)}[/yellow]")
            sys.exit(1)
    else:
        sources_to_run = ALL_SOURCES
    
    # Collect signals
    result = await collect_all_signals(
        sources_to_run=sources_to_run,
        limit=args.limit,
        days=args.days,
        min_engagement=args.min_engagement
    )
    
    # Output
    if args.json:
        output_json(result)
    else:
        print_summary(result)
        
        if args.save:
            save_to_file(result)


if __name__ == "__main__":
    asyncio.run(main())


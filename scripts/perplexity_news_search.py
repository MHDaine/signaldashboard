#!/usr/bin/env python3
"""
Perplexity News Search Script

Uses Perplexity's Agent API with pro-search preset to find
recent news (last 7 days) based on company context from context_summary.md.

Generates 3 news-focused queries based on company topics and collects
signal URLs from search results, capped at 50 signals per query.

Usage:
    python scripts/perplexity_news_search.py                    # Run with auto-generated queries
    python scripts/perplexity_news_search.py --queries "q1,q2"  # Custom queries
    python scripts/perplexity_news_search.py --limit 50         # Signals per query (default: 50)
    python scripts/perplexity_news_search.py --json             # Output JSON to stdout
    python scripts/perplexity_news_search.py --save             # Save to file
"""

import sys
import os
import json
import re
import argparse
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
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_API_URL = "https://api.perplexity.ai/v1/responses"
CONTEXT_FILE = "context/context_summary.md"

# News query templates based on company focus areas
NEWS_QUERY_TEMPLATES = [
    "Latest news and developments in AI marketing automation and AI-powered marketing tools from the past week",
    "Recent news about fractional CMO services, marketing talent marketplaces, and marketing agency industry trends",
    "Breaking news on B2B SaaS marketing strategies, growth marketing trends, and marketing technology investments",
]


def load_context_summary() -> str:
    """Load the context summary from the context folder."""
    context_path = Path(__file__).parent.parent / CONTEXT_FILE
    
    if not context_path.exists():
        console.print(f"[yellow]Warning: {CONTEXT_FILE} not found, using default queries[/yellow]")
        return ""
    
    with open(context_path, 'r') as f:
        return f.read()


def generate_news_queries(context: str) -> List[str]:
    """Generate 3 news-focused queries based on company context."""
    
    if not context:
        return NEWS_QUERY_TEMPLATES
    
    # Extract key themes from context
    # Focus on: AI marketing, marketing automation, fractional CMO, talent marketplace, B2B SaaS
    
    queries = [
        # Query 1: AI Marketing & Automation trends
        "What are the latest news and developments in AI marketing automation, "
        "AI-powered marketing tools, and marketing AI adoption in enterprise companies "
        "from the past 7 days? Include funding news, product launches, and industry analysis.",
        
        # Query 2: Marketing services & agency industry
        "What are the recent news about marketing agencies, fractional CMO services, "
        "marketing talent platforms, and changes in how companies hire marketing expertise "
        "from the past week? Include market trends and competitive developments.",
        
        # Query 3: B2B SaaS & Growth marketing
        "What are the breaking news on B2B SaaS marketing strategies, growth marketing trends, "
        "marketing technology investments, and CMO/marketing leadership changes "
        "from the past 7 days? Focus on venture-backed and mid-market companies.",
    ]
    
    return queries


async def search_with_perplexity(
    query: str,
    recency_days: int = 7
) -> Dict[str, Any]:
    """Execute a Perplexity pro-search query."""
    
    if not PERPLEXITY_API_KEY:
        console.print("[red]Error: PERPLEXITY_API_KEY not configured[/red]")
        return {"content": "", "sources": []}
    
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Calculate date filter
    after_date = (datetime.now() - timedelta(days=recency_days)).strftime("%-m/%-d/%Y")
    
    payload = {
        "preset": "pro-search",  # Balanced for accurate, well-researched responses
        "input": query,
        "tools": [
            {
                "type": "web_search",
                "filters": {
                    "search_recency_filter": "week",
                    "search_after_date": after_date
                }
            }
        ],
        "instructions": (
            "You are a marketing industry analyst. Search for recent news articles, "
            "press releases, and industry reports. For each piece of news, provide: "
            "1) A clear headline summary, 2) Key details and implications, "
            "3) The source name. Focus on factual reporting from the past 7 days. "
            "Prioritize news from reputable business and marketing publications."
        )
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                PERPLEXITY_API_URL,
                headers=headers,
                json=payload,
                timeout=60.0  # Pro-search is faster than deep-research
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract content and sources
                content = ""
                sources = []
                
                # Parse output based on response structure
                if "output" in data:
                    for item in data["output"]:
                        if item.get("type") == "text":
                            content = item.get("text", "")
                        elif item.get("type") == "search_results":
                            for result in item.get("results", []):
                                sources.append({
                                    "title": result.get("title", ""),
                                    "url": result.get("url", ""),
                                    "snippet": result.get("snippet", ""),
                                    "date": result.get("date", "")
                                })
                
                # Also check for output_text (simpler format)
                if not content and "output_text" in data:
                    content = data["output_text"]
                
                # Check for search_results at top level
                if not sources and "search_results" in data:
                    for result in data["search_results"]:
                        sources.append({
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "snippet": result.get("snippet", ""),
                            "date": result.get("date", "")
                        })
                
                return {
                    "content": content,
                    "sources": sources,
                    "raw": data
                }
            
            elif response.status_code == 429:
                console.print(f"[yellow]⚠️ Rate limited[/yellow]")
                return {"content": "", "sources": [], "error": "rate_limited"}
            
            else:
                error_text = response.text[:300]
                console.print(f"[red]Error {response.status_code}: {error_text}[/red]")
                return {"content": "", "sources": [], "error": error_text}
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return {"content": "", "sources": [], "error": str(e)}


def extract_urls_from_content(content: str) -> List[str]:
    """Extract URLs mentioned in the content."""
    # Match common URL patterns
    url_pattern = r'https?://[^\s\]\)>"\']+'
    urls = re.findall(url_pattern, content)
    return list(set(urls))


def transform_to_signal(
    source: Dict[str, Any],
    query: str,
    query_index: int
) -> Dict[str, Any]:
    """Transform a Perplexity source to signal format."""
    
    return {
        "id": f"pplx-{hash(source.get('url', '')) % 100000:05d}",
        "type": "perplexity-news",
        "source": "perplexity-pro-search",
        "query": query[:100],
        "query_index": query_index,
        "title": source.get("title", "")[:200],
        "content": source.get("snippet", ""),
        "date_posted": source.get("date", ""),
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "url": source.get("url", ""),
        "engagement": {
            "relevance": "high"  # Pro-search returns well-researched results
        },
        "status": "unused",
    }


async def collect_perplexity_news(
    queries: List[str],
    recency_days: int = 7,
    limit_per_query: int = 50
) -> List[Dict[str, Any]]:
    """Collect news signals using Perplexity pro-search.
    
    Args:
        queries: List of search queries to run.
        recency_days: How many days back to search.
        limit_per_query: Max signals to keep per query (default: 50).
    """
    
    all_signals = []
    all_content = []
    seen_urls = set()
    
    console.print(Panel(
        f'[bold cyan]Perplexity News Search[/bold cyan]\n\n'
        f'Queries: {len(queries)}\n'
        f'Preset: pro-search\n'
        f'Limit: {limit_per_query} signals per query\n'
        f'Recency: Last {recency_days} days',
        border_style='cyan'
    ))
    
    for i, query in enumerate(queries, 1):
        console.print(f"\n[yellow][{i}/{len(queries)}] Searching:[/yellow]")
        console.print(f"   [dim]{query[:80]}...[/dim]")
        
        result = await search_with_perplexity(query, recency_days)
        
        if result.get("error"):
            console.print(f"   [red]✗ Error: {result['error'][:50]}[/red]")
            continue
        
        sources = result.get("sources", [])
        content = result.get("content", "")
        
        # Store content for summary
        if content:
            all_content.append({
                "query": query,
                "content": content
            })
        
        # Transform sources to signals, capped at limit_per_query
        query_signals = []
        for source in sources:
            if len(query_signals) >= limit_per_query:
                break
            
            url = source.get("url", "")
            
            # Deduplicate by URL
            if url and url not in seen_urls:
                seen_urls.add(url)
                signal = transform_to_signal(source, query, i)
                query_signals.append(signal)
        
        all_signals.extend(query_signals)
        console.print(f"   [green]✓ Found {len(query_signals)} sources (cap: {limit_per_query})[/green]")
    
    return all_signals, all_content


def print_summary(signals: List[Dict[str, Any]], content: List[Dict[str, Any]]):
    """Print collection summary."""
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ COLLECTION COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Signals: [bold]{len(signals)}[/bold]\n")
    
    if not signals:
        console.print("[yellow]No news sources found.[/yellow]")
        return
    
    # Group by query
    by_query = {}
    for s in signals:
        q_idx = s.get("query_index", 0)
        by_query[q_idx] = by_query.get(q_idx, 0) + 1
    
    table = Table(title="Sources by Query", show_header=True, header_style="bold magenta")
    table.add_column("Query #", width=10, justify="center")
    table.add_column("Sources", width=10, justify="center")
    
    for q_idx, count in sorted(by_query.items()):
        table.add_row(f"Query {q_idx}", str(count))
    
    console.print(table)
    
    # Show sample signals
    console.print("\n[bold]Sample News Sources:[/bold]\n")
    
    for i, s in enumerate(signals[:5], 1):
        console.print(f"[magenta]{i}. {s['title'][:70]}...[/magenta]")
        if s.get('date_posted'):
            console.print(f"   [dim]Date: {s['date_posted']}[/dim]")
        console.print(f"   [cyan]🔗 {s['url'][:70]}...[/cyan]")
        console.print()
    
    # Show content summaries
    if content:
        console.print("\n[bold]Research Summaries:[/bold]\n")
        for i, c in enumerate(content, 1):
            console.print(f"[yellow]Query {i}:[/yellow]")
            # Show first 300 chars of content
            summary = c['content'][:300].replace('\n', ' ')
            console.print(f"   {summary}...")
            console.print()


def output_json(signals: List[Dict[str, Any]], content: List[Dict[str, Any]]):
    """Output signals as JSON to stdout."""
    output = {
        "platform": "perplexity",
        "source_type": "pro-search-news",
        "collected_at": datetime.now().isoformat(),
        "count": len(signals),
        "signals": signals,
        "research_summaries": [
            {"query": c["query"], "summary": c["content"][:1000]}
            for c in content
        ]
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def save_to_file(signals: List[Dict[str, Any]], content: List[Dict[str, Any]], filename: str = None):
    """Save signals to JSON file."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"outputs/perplexity_news_{timestamp}.json"
    
    Path("outputs").mkdir(exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": "perplexity",
            "source_type": "pro-search-news",
            "collected_at": datetime.now().isoformat(),
            "count": len(signals),
            "signals": signals,
            "research_summaries": [
                {"query": c["query"], "summary": c["content"]}
                for c in content
            ]
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Saved to: {filename}[/green]")
    return filename


async def main():
    """Main entry point."""
    import asyncio
    
    parser = argparse.ArgumentParser(
        description='Perplexity News Search - Deep research for recent news based on company context'
    )
    parser.add_argument('--queries', type=str, default=None,
                       help='Comma-separated custom queries (overrides auto-generated)')
    parser.add_argument('--days', type=int, default=7,
                       help='Recency filter in days (default: 7)')
    parser.add_argument('--limit', type=int, default=50,
                       help='Max signals per query (default: 50)')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON to stdout')
    parser.add_argument('--save', action='store_true',
                       help='Save to file in outputs/')
    
    args = parser.parse_args()
    
    # Check API key
    if not PERPLEXITY_API_KEY:
        console.print("[red]Error: PERPLEXITY_API_KEY not set in .env[/red]")
        console.print("[yellow]Get your API key at: https://www.perplexity.ai/settings/api[/yellow]")
        sys.exit(1)
    
    # Load queries
    if args.queries:
        queries = [q.strip() for q in args.queries.split(',')]
    else:
        # Generate queries based on context
        context = load_context_summary()
        queries = generate_news_queries(context)
    
    if not queries:
        console.print("[red]Error: No queries to search[/red]")
        sys.exit(1)
    
    # Show queries
    console.print("[bold]Generated News Queries:[/bold]")
    for i, q in enumerate(queries, 1):
        console.print(f"  {i}. {q[:80]}...")
    
    # Collect signals
    signals, content = await collect_perplexity_news(
        queries=queries,
        recency_days=args.days,
        limit_per_query=args.limit
    )
    
    # Output
    if args.json:
        output_json(signals, content)
    else:
        print_summary(signals, content)
        
        if args.save:
            save_to_file(signals, content)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


#!/usr/bin/env python3
"""
Signal Enrichment Script

Uses Perplexity deep-research to add context, analysis, and MH-1 perspective
to approved signals. Fetches additional information from URLs and generates
founder-specific talking points.

Usage:
    python scripts/enrich_signals.py approved_signals.json
    python scripts/enrich_signals.py approved_signals.json --save
    python scripts/enrich_signals.py approved_signals.json --batch-size 3
"""

import sys
import os
import json
import argparse
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

load_dotenv()

console = Console(stderr=True)  # rich output to stderr, keep stdout clean for PROGRESS lines

# Configuration
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

CONTEXT_FILE = "context/context_summary.md"
POV_FILE = "context/pov.md"

# MH-1 Founder Information for perspective matching
MH1_FOUNDERS = {
    "chris_toy": {
        "name": "Chris Toy",
        "role": "CEO",
        "pillars": [
            "The Death of Attribution",
            "The Talent Cloud",
            "Fundamentals Over Fads", 
            "The Agency Model Is Broken",
            "AI as Marketing Superpower"
        ],
        "voice": "Strategic, contrarian, focused on outcomes over activities"
    },
    "raaja_nemani": {
        "name": "Raaja Nemani",
        "role": "Co-Founder",
        "pillars": [
            "Community as Competitive Moat",
            "Attention to Detail as Speed Multiplier",
            "The Individual as Media Brand",
            "Finance Rigor Meets Creative Execution"
        ],
        "voice": "Analytical, community-focused, execution-oriented"
    },
    "cameron_rzonca": {
        "name": "Cameron Rzonca", 
        "role": "AI Operations",
        "pillars": [
            "From AI Tools to AI Systems",
            "Human + AI Hybrid Model",
            "Data-Driven Creativity",
            "Enterprise Scale for Growing Companies"
        ],
        "voice": "Technical, systems-thinking, operational excellence"
    },
    "nikhil_arora": {
        "name": "Nikhil Arora",
        "role": "Growth",
        "pillars": [
            "P&L-Driven Growth",
            "Cross-Industry Growth Playbooks",
            "Depersonalizing Failure",
            "AI for Operating Leverage"
        ],
        "voice": "Data-driven, growth-focused, unit economics minded"
    }
}

ENRICHMENT_PROMPT = """You are a senior content strategist for MH-1 (MarketerHire's AI Marketing System).

Your task is to deeply research and enrich this signal for thought leadership content creation.

## Company Context
MH-1 is a "Full-Stack Human + AI Marketing System" that replaces the traditional agency model with AI-powered workflows. Target: mid-market companies ($10M-$100M ARR).

## Signal to Enrich

**Title:** {title}
**Source:** {source}
**URL:** {url}
**Original Content:** {content}
**Ranking Score:** {score}
**Suggested Founder:** {founder}

## Your Research Tasks

1. **Deep Dive on Topic**: Research the broader context around this signal. What's the full story? What are others saying? What data supports or contradicts this?

2. **Market Impact Analysis**: How does this affect marketing leaders, CMOs, and growing companies? What should they do about it?

3. **MH-1 Perspective**: How does this relate to MH-1's positioning? What unique angle can we bring that others won't?

4. **Founder Voice Match**: Based on the suggested founder ({founder_name}), craft talking points that match their voice and content pillars:
   - Voice: {founder_voice}
   - Pillars: {founder_pillars}

5. **Content Angles**: Suggest 3 specific content angles for LinkedIn posts, each with a hook and key message.

## Response Format
Respond with ONLY valid JSON (no markdown code blocks):
{{
    "deep_research_summary": "<2-3 paragraphs of researched context and analysis>",
    "key_data_points": ["<stat or data point 1>", "<stat or data point 2>", "<stat or data point 3>"],
    "market_impact": {{
        "for_cmos": "<1-2 sentences on CMO implications>",
        "for_growth_teams": "<1-2 sentences on growth team implications>",
        "for_agencies": "<1-2 sentences on agency implications>"
    }},
    "mh1_angle": "<unique MH-1 perspective that differentiates from generic takes>",
    "founder_talking_points": [
        "<talking point 1 in founder's voice>",
        "<talking point 2 in founder's voice>",
        "<talking point 3 in founder's voice>"
    ],
    "content_angles": [
        {{
            "hook": "<attention-grabbing opening line>",
            "key_message": "<core insight to convey>",
            "cta_direction": "<what action/thought to leave reader with>"
        }},
        {{
            "hook": "<attention-grabbing opening line>",
            "key_message": "<core insight to convey>",
            "cta_direction": "<what action/thought to leave reader with>"
        }},
        {{
            "hook": "<attention-grabbing opening line>",
            "key_message": "<core insight to convey>",
            "cta_direction": "<what action/thought to leave reader with>"
        }}
    ],
    "related_sources": ["<url 1 from research>", "<url 2 from research>"],
    "confidence_score": <0-100 based on research quality>
}}
"""


def load_context() -> str:
    """Load company context."""
    context = ""
    if Path(CONTEXT_FILE).exists():
        with open(CONTEXT_FILE, 'r') as f:
            context = f.read()
    return context


def load_signals(filepath: str) -> List[Dict[str, Any]]:
    """Load signals from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Handle both direct list and wrapped format
    if isinstance(data, list):
        return data
    return data.get("signals", data.get("approved_signals", []))


def get_founder_info(founder_key: str) -> Dict[str, Any]:
    """Get founder information for enrichment."""
    founder = MH1_FOUNDERS.get(founder_key, MH1_FOUNDERS.get("chris_toy"))
    return founder


async def _call_perplexity(prompt: str, client: httpx.AsyncClient) -> dict:
    """Make a single Perplexity API call and return the raw response data."""
    response = await client.post(
        PERPLEXITY_API_URL,
        headers={
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "sonar-deep-research",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a senior content strategist and researcher. Always respond with valid JSON only, no markdown formatting."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "max_tokens": 4000,
            "return_citations": True
        },
        timeout=120.0  # Deep research can take longer
    )
    response.raise_for_status()
    return response.json()


def _extract_json_from_content(raw_content: str) -> str:
    """Clean Perplexity response content and extract JSON string."""
    content = raw_content.strip()

    # Strip markdown code blocks
    if content.startswith("```"):
        content = re.sub(r'^```json?\n?', '', content)
        content = re.sub(r'\n?```\s*$', '', content)
        content = content.strip()

    # Try to extract the outermost JSON object
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        content = json_match.group(0)

    return content


async def enrich_signal_with_perplexity(
    signal: Dict[str, Any],
    client: httpx.AsyncClient,
    max_retries: int = 2
) -> Dict[str, Any]:
    """Enrich a single signal using Perplexity deep research.
    
    Retries up to `max_retries` times on transient/parse errors.
    """
    
    # Extract signal data
    ranking = signal.get("ranking", {})
    founder_key = ranking.get("best_founder", "chris_toy")
    founder = get_founder_info(founder_key)
    
    prompt = ENRICHMENT_PROMPT.format(
        title=signal.get("title", "")[:200],
        source=signal.get("collection_source", signal.get("type", "unknown")),
        url=signal.get("url", ""),
        content=signal.get("content", "")[:1500],
        score=ranking.get("total_score", 0),
        founder=founder_key,
        founder_name=founder.get("name", ""),
        founder_voice=founder.get("voice", ""),
        founder_pillars=", ".join(founder.get("pillars", []))
    )
    
    last_error = ""
    for attempt in range(1, max_retries + 2):  # 1 initial + max_retries
        try:
            data = await _call_perplexity(prompt, client)
            
            # Extract content and citations
            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            citations = data.get("citations", [])
            
            if not raw_content or not raw_content.strip():
                last_error = "Empty response from Perplexity"
                if attempt <= max_retries:
                    console.print(f"[yellow]  ↻ Empty response, retrying ({attempt}/{max_retries})…[/yellow]")
                    await asyncio.sleep(2 * attempt)
                    continue
                return {
                    "signal_id": signal.get("id", ""),
                    "original_signal": signal,
                    "enrichment": None,
                    "enriched_at": datetime.now().isoformat(),
                    "error": last_error
                }
            
            # Clean and extract JSON
            content = _extract_json_from_content(raw_content)
            
            if not content or not content.strip():
                last_error = f"No JSON found after cleaning response ({len(raw_content)} chars raw)"
                if attempt <= max_retries:
                    console.print(f"[yellow]  ↻ No JSON in response, retrying ({attempt}/{max_retries})…[/yellow]")
                    await asyncio.sleep(2 * attempt)
                    continue
                return {
                    "signal_id": signal.get("id", ""),
                    "original_signal": signal,
                    "enrichment": None,
                    "enriched_at": datetime.now().isoformat(),
                    "error": last_error
                }
            
            # Parse JSON response
            enrichment = json.loads(content)
            
            # Add citations from Perplexity
            if citations:
                existing_sources = enrichment.get("related_sources", [])
                for citation in citations[:5]:  # Limit to 5 additional sources
                    if isinstance(citation, dict):
                        existing_sources.append(citation.get("url", ""))
                    elif isinstance(citation, str):
                        existing_sources.append(citation)
                enrichment["related_sources"] = list(set(existing_sources))[:8]
            
            return {
                "signal_id": signal.get("id", ""),
                "original_signal": signal,
                "enrichment": enrichment,
                "enriched_at": datetime.now().isoformat(),
                "error": None
            }
            
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {str(e)[:100]}"
            if attempt <= max_retries:
                console.print(f"[yellow]  ↻ JSON parse failed, retrying ({attempt}/{max_retries})…[/yellow]")
                await asyncio.sleep(2 * attempt)
                continue
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            last_error = f"API error: {status_code} - {e.response.text[:100]}"
            # Retry on 429 (rate limit) and 5xx (server errors)
            if status_code in (429, 500, 502, 503, 504) and attempt <= max_retries:
                wait = 5 * attempt if status_code == 429 else 2 * attempt
                console.print(f"[yellow]  ↻ HTTP {status_code}, retrying in {wait}s ({attempt}/{max_retries})…[/yellow]")
                await asyncio.sleep(wait)
                continue
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_error = f"Connection error: {str(e)[:100]}"
            if attempt <= max_retries:
                console.print(f"[yellow]  ↻ Connection issue, retrying ({attempt}/{max_retries})…[/yellow]")
                await asyncio.sleep(3 * attempt)
                continue
        except Exception as e:
            last_error = str(e)[:100]
            if attempt <= max_retries:
                console.print(f"[yellow]  ↻ Error: {last_error}, retrying ({attempt}/{max_retries})…[/yellow]")
                await asyncio.sleep(2 * attempt)
                continue
    
    # All retries exhausted
    return {
        "signal_id": signal.get("id", ""),
        "original_signal": signal,
        "enrichment": None,
        "enriched_at": datetime.now().isoformat(),
        "error": last_error
    }


def emit_progress(
    completed: int, total: int, success_count: int, error_count: int,
    current_title: str = "", status: str = "running"
):
    """Emit enrichment progress as a JSON line to stdout so the frontend can read it.
    
    Uses os.write(1, ...) to bypass rich's Progress context manager which
    intercepts sys.stdout and wraps/splits long lines at terminal width.
    """
    try:
        line = "PROGRESS:" + json.dumps({
            "completed": completed,
            "total": total,
            "success_count": success_count,
            "error_count": error_count,
            "current_title": current_title,
            "status": status,
        }) + "\n"
        os.write(1, line.encode())
    except Exception:
        pass


async def enrich_signals(
    signals: List[Dict[str, Any]],
    batch_size: int = 2
) -> List[Dict[str, Any]]:
    """Enrich all signals using Perplexity."""
    
    if not PERPLEXITY_API_KEY:
        console.print("[red]Error: PERPLEXITY_API_KEY not set in .env[/red]")
        sys.exit(1)
    
    console.print(Panel(
        f'[bold cyan]Signal Enrichment System[/bold cyan]\n\n'
        f'Signals to enrich: {len(signals)}\n'
        f'Model: sonar-deep-research\n'
        f'Batch size: {batch_size}',
        border_style='cyan'
    ))
    
    enriched_signals = []
    success_count = 0
    error_count = 0
    completed = 0
    total = len(signals)
    
    # Emit initial progress
    emit_progress(0, total, 0, 0, "", "running")
    
    async with httpx.AsyncClient() as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Enriching signals...", total=total)
            
            # Process in batches, stream results as they arrive
            for i in range(0, total, batch_size):
                batch = signals[i:i + batch_size]
                
                # Show what we're enriching
                titles = [s.get("title", "Untitled")[:50] for s in batch]
                console.print(f"[dim]Enriching: {', '.join(titles)}...[/dim]")
                
                # Enrich batch concurrently
                coros = [
                    enrich_signal_with_perplexity(signal, client)
                    for signal in batch
                ]
                
                for future in asyncio.as_completed(coros):
                    try:
                        result = await future
                    except Exception as e:
                        console.print(f"[red]Error: {e}[/red]")
                        error_count += 1
                        completed += 1
                        emit_progress(completed, total, success_count, error_count, "", "running")
                        progress.update(task, advance=1)
                        continue
                    
                    if result.get("error"):
                        error_count += 1
                        console.print(f"[yellow]⚠️ {result.get('error')}[/yellow]")
                    else:
                        success_count += 1
                    
                    enriched_signals.append(result)
                    completed += 1
                    
                    title = result.get("original_signal", {}).get("title", "")[:60]
                    emit_progress(completed, total, success_count, error_count, title, "running")
                    progress.update(task, advance=1)
                
                # Rate limit between batches
                if i + batch_size < total:
                    await asyncio.sleep(2)  # Be gentle with rate limits
    
    # Emit final progress
    emit_progress(total, total, success_count, error_count, "", "complete")
    
    if error_count > 0:
        console.print(f"\n[yellow]⚠️ {error_count} signals had enrichment errors[/yellow]")
    
    return enriched_signals


def print_summary(enriched_signals: List[Dict[str, Any]]):
    """Print enrichment summary."""
    
    successful = [s for s in enriched_signals if s.get("enrichment")]
    failed = [s for s in enriched_signals if not s.get("enrichment")]
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ ENRICHMENT COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Processed: [bold]{len(enriched_signals)}[/bold]")
    console.print(f"✅ Successfully Enriched: [bold green]{len(successful)}[/bold green]")
    console.print(f"❌ Failed: [bold red]{len(failed)}[/bold red]\n")
    
    # Show sample of enriched content
    if successful:
        console.print("[bold]Sample Enriched Signal:[/bold]\n")
        sample = successful[0]
        enrichment = sample.get("enrichment", {})
        original = sample.get("original_signal", {})
        
        console.print(f"[cyan]Title:[/cyan] {original.get('title', '')[:60]}...")
        console.print(f"[cyan]URL:[/cyan] {original.get('url', '')}")
        console.print(f"\n[cyan]MH-1 Angle:[/cyan]")
        console.print(f"  {enrichment.get('mh1_angle', 'N/A')[:200]}...")
        
        console.print(f"\n[cyan]Key Data Points:[/cyan]")
        for dp in enrichment.get("key_data_points", [])[:3]:
            console.print(f"  • {dp[:100]}")
        
        console.print(f"\n[cyan]Content Angles:[/cyan]")
        for i, angle in enumerate(enrichment.get("content_angles", [])[:2], 1):
            console.print(f"  {i}. Hook: {angle.get('hook', '')[:80]}...")
        
        console.print(f"\n[cyan]Related Sources:[/cyan]")
        for src in enrichment.get("related_sources", [])[:3]:
            console.print(f"  • {src}")


ENRICHED_FILE = "outputs/enriched_signals.json"


def save_to_file(enriched_signals: List[Dict[str, Any]], filename: str = None):
    """Save enriched signals to file."""
    filename = filename or ENRICHED_FILE
    
    Path("outputs").mkdir(exist_ok=True)
    
    successful = [s for s in enriched_signals if s.get("enrichment")]
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            "enriched_at": datetime.now().isoformat(),
            "total_signals": len(enriched_signals),
            "successful_count": len(successful),
            "signals": enriched_signals
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Saved {len(successful)} enriched signals to: {filename}[/green]")
    return filename


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description='Enrich approved signals with Perplexity deep research'
    )
    parser.add_argument('input_file', type=str,
                       help='Path to approved signals JSON file')
    parser.add_argument('--batch-size', type=int, default=2,
                       help='Batch size for API calls (default: 2)')
    parser.add_argument('--save', action='store_true',
                       help='Save to file in outputs/')
    parser.add_argument('--output', type=str, default=None,
                       help='Custom output filename')
    
    args = parser.parse_args()
    
    # Check input file exists
    if not Path(args.input_file).exists():
        console.print(f"[red]Error: File not found: {args.input_file}[/red]")
        sys.exit(1)
    
    # Check API key
    if not PERPLEXITY_API_KEY:
        console.print("[red]Error: PERPLEXITY_API_KEY not set in .env[/red]")
        sys.exit(1)
    
    # Load signals
    console.print(f"[dim]Loading signals from: {args.input_file}[/dim]")
    signals = load_signals(args.input_file)
    
    if not signals:
        console.print("[red]Error: No signals found in file[/red]")
        sys.exit(1)
    
    console.print(f"[dim]Found {len(signals)} signals to enrich[/dim]")
    
    # Enrich signals
    enriched_signals = await enrich_signals(
        signals=signals,
        batch_size=args.batch_size
    )
    
    # Output
    print_summary(enriched_signals)
    
    if args.save or args.output:
        save_to_file(enriched_signals, args.output)


if __name__ == "__main__":
    asyncio.run(main())


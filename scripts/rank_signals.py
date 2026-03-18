#!/usr/bin/env python3
"""
Signal Ranking System

Ranks collected signals using OpenAI gpt-5-nano based on weighted criteria
tailored for MH-1 (MarketerHire's AI Marketing System).

Litmus Test: "Is this marketing/AI news that MH-1's ICPs would find interesting?"

Scoring Criteria:
- ICP Interest (45%): Would a VP Marketing / CEO / CMO at a $10-100M company care about this?
- Timeliness (30%): How recent? Strongly favor last 24-72h
- News Quality (25%): Is this real news/data, not fluff?

Usage:
    python scripts/rank_signals.py outputs/all_signals_*.json
    python scripts/rank_signals.py outputs/all_signals_*.json --min-score 60
    python scripts/rank_signals.py outputs/all_signals_*.json --top 50
    python scripts/rank_signals.py outputs/all_signals_*.json --save
"""

import sys
import os
import json
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore
from openai import AsyncOpenAI
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

load_dotenv()

console = Console(stderr=True)  # rich output to stderr, keep stdout clean for PROGRESS lines

# Configuration - support OPENAI_KEY and OPENAI_API_KEY
OPENAI_API_KEY = os.environ.get("OPENAI_KEY") or os.environ.get("OPENAI_API_KEY")

CONTEXT_FILE = "context/context_summary.md"
POV_FILE = "context/pov.md"
FIREBASE_COLLECTION = os.environ.get("COLLECTION", "mh_newsletter")
FIREBASE_FEEDBACK_DOC = "feedback"

# Model to use - gpt-5-nano is the cheapest/fastest OpenAI model
OPENAI_MODEL = "gpt-5-nano-2025-08-07"

# Scoring weights — "Is this marketing/AI news that MH-1's ICPs would find interesting?"
SCORING_WEIGHTS = {
    "icp_interest": 0.45,          # 45% - LITMUS TEST: Would a VP Marketing / CEO / CMO at a $10-100M company care about this?
    "timeliness": 0.30,            # 30% - How recent? Strongly favor last 24-72h
    "news_quality": 0.25,          # 25% - Is this real news/data, not fluff?
}

# MH-1 Content Pillars and Themes (from context_summary.md)
MH1_THEMES = """
## MH-1 Core Themes & Content Pillars

### Company Focus
- AI-native marketing system ("Full-Stack Human + AI Marketing System")
- Replacing traditional agency model with AI-powered workflows
- Mid-market and venture-backed companies ($10M-$100M ARR)
- Month-to-month flexibility vs. 12-month agency lock-ins

### Key Content Pillars

**Chris Toy (CEO):**
- The Death of Attribution (privacy changes, measurement resilience)
- The Talent Cloud (on-demand marketing specialists)
- Fundamentals Over Fads (channel agnosticism, timeless principles)
- The Agency Model Is Broken (outcome-based vs. hours-based billing)
- AI as Marketing Superpower (adoption gap, workflow integration)

**Raaja Nemani (Co-Founder):**
- Community as Competitive Moat (network effects, trust)
- Attention to Detail as Speed Multiplier ("measure twice, cut once")
- The Individual as Media Brand (thought leadership ROI)
- Finance Rigor Meets Creative Execution (CFO-CMO alignment)

**Cameron Rzonca (AI Operations):**
- From AI Tools to AI Systems (intelligence layers, competitive advantage)
- Human + AI Hybrid Model (adaptation, not replacement)
- Data-Driven Creativity (pattern recognition in marketing)
- Enterprise Scale for Growing Companies (Fortune 500 tactics for growth stage)

**Nikhil Arora (Growth):**
- P&L-Driven Growth (unit economics, full revenue equation)
- Cross-Industry Growth Playbooks (universal acquisition principles)
- Depersonalizing Failure (safe-to-fail cultures)
- AI for Operating Leverage (doing more with less)

### Target Audience Pain Points
- AI Adoption Gap: Using AI tools but not seeing EBIT impact
- Vendor Fragmentation: Managing 5+ marketing vendors/agencies
- Headcount Constraints: Need enterprise capabilities but can't hire
- Speed vs. Quality Trade-off: Agencies too slow, freelancers inconsistent

### Topics to PRIORITIZE (TOFU Industry Themes)
- AI/ML in marketing and automation trends
- Marketing attribution and measurement challenges
- Fractional/flexible marketing talent models
- Marketing ROI and efficiency metrics
- CMO/marketing leadership challenges
- B2B SaaS growth strategies
- Marketing technology evolution
- Agency industry disruption

### Topics to AVOID (BOFU Product Features)
- Direct product pitches or feature comparisons
- "MH-1 solves this" as the primary angle
- Competitor bashing or sales-focused content
"""

SCORING_PROMPT = """You are scoring signals for MH-1 (MarketerHire's AI Marketing System).

## The Litmus Test
**"Is this marketing or AI news that would be interesting to MH-1's ICPs?"**

MH-1's ICPs are:
- **VP of Marketing / Head of Growth** at mid-market companies ($10M-$100M ARR) — managing multiple agencies, trying to prove AI ROI, dealing with headcount freezes
- **Founder / CEO** of growth-stage startups (30-150 employees) — wants marketing that runs without daily oversight, burned by agencies, needs AI strategy
- **First-Time CMO** at scaling companies — 90-day pressure to show results, inherited chaos, proving ROI on "modern marketing"

They care about: AI transforming marketing operations, marketing attribution & measurement, fractional/flexible talent models, agency model disruption, martech consolidation, CMO challenges, B2B SaaS growth, marketing efficiency & ROI, AI adoption gaps, and marketing automation.

They do NOT care about: generic tech news, consumer product launches unrelated to marketing, crypto/web3, celebrity news, general business news with no marketing angle, self-help, or job postings.
{feedback_context}
## Signal to Score

**Source:** {source}
**Title:** {title}
**Content:** {content}
**URL:** {url}

## Scoring Criteria (score each 0-100)

1. **ICP Interest (45%) — THE LITMUS TEST**: Would a VP Marketing, CEO, or CMO at a $10M-$100M company read this and think "I need to know about this"?
   - Score 80-100: Directly about marketing + AI intersection, agency/talent model shifts, marketing leadership challenges, martech funding/launches, marketing measurement, or growth strategy news. Something these people would share with their team or bring up in a meeting.
   - Score 50-79: Tangentially relevant — general AI news that has marketing implications, SaaS industry trends, business strategy that affects marketing teams.
   - Score 0-49: Not marketing/AI news. General tech, unrelated industries, consumer news, job postings, pure self-promotion, motivational content.

2. **Timeliness (30%)**: How recent is this?
   - Score 80-100: Last 24-72 hours — breaking or very fresh
   - Score 50-79: Last 1-2 weeks
   - Score 0-49: Older than 2 weeks, undated, or evergreen/recycled content

3. **News Quality (25%)**: Is this real news with substance, or fluff?
   - Score 80-100: Hard news — funding rounds, product launches, research/data with numbers, acquisitions, executive moves, regulatory changes, market reports
   - Score 50-79: Informed analysis backed by specific data or referencing specific recent developments
   - Score 0-49: Pure opinion without data, generic advice, thought leadership fluff, self-promotion, job postings

## Response Format
Respond with ONLY valid JSON (no markdown):
{{
    "icp_interest": <0-100>,
    "timeliness": <0-100>,
    "news_quality": <0-100>,
    "news_type": "<funding|product_launch|research_data|industry_event|market_report|executive_move|regulatory|opinion|advice|job_posting|other>",
    "news_summary": "<One-sentence summary: what is the news and why would an ICP care?>"
}}
"""


def load_context() -> str:
    """Load context for scoring — uses context_summary.md if available, falls back to MH1_THEMES."""
    context_path = Path(CONTEXT_FILE)
    if context_path.exists():
        with open(context_path, 'r') as f:
            full_context = f.read()
        # Extract just the Content Pillars and Competitive sections to keep prompt manageable
        # but still provide rich context for scoring
        return full_context[:4000]  # First ~4000 chars covers pillars + audience
    return MH1_THEMES


def _init_firebase():
    if firebase_admin._apps:
        return
    sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        cred = fb_credentials.Certificate(info)
    else:
        sa_file = os.environ.get("SERVICE_ACCOUNT", "")
        if sa_file and Path(sa_file).exists():
            cred = fb_credentials.Certificate(sa_file)
        else:
            return  # silently skip — feedback is optional for ranking
    firebase_admin.initialize_app(cred)


def load_feedback_context() -> str:
    """Load rejection feedback from Firestore and summarize for the scoring prompt."""
    try:
        _init_firebase()
        if not firebase_admin._apps:
            return ""
        db = firestore.client()
        doc = db.collection(FIREBASE_COLLECTION).document(FIREBASE_FEEDBACK_DOC).get()
        if not doc.exists:
            return ""
        entries = doc.to_dict().get("feedback", [])
    except Exception:
        return ""

    if not entries:
        return ""

    recent = entries[-50:]

    lines = ["\n## Rejection Feedback (from human review)",
             "The following signals have been rejected by reviewers. Penalize signals matching these patterns:"]
    for entry in recent:
        title = entry.get("signal_title", "unknown signal")
        summary = entry.get("signal_summary", "")
        reason = entry.get("rejection_reason", "")
        if reason:
            label = f'"{title}"'
            if summary:
                label += f' ({summary})'
            lines.append(f'- {label} — {reason}')

    if len(lines) == 2:
        return ""

    return "\n".join(lines) + "\n"


def load_signals(filepath: str) -> List[Dict[str, Any]]:
    """Load signals from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    return data.get("signals", [])


def get_signal_content(signal: Dict[str, Any]) -> str:
    """Extract content from signal for scoring."""
    content = signal.get("content", "")
    title = signal.get("title", "")
    
    # Combine title and content, limit length
    full_content = f"{title}\n\n{content}" if title else content
    return full_content[:2000]  # Limit to 2000 chars for API efficiency


def get_engagement_str(signal: Dict[str, Any]) -> str:
    """Format engagement data for display."""
    engagement = signal.get("engagement", {})
    source = signal.get("collection_source", "") or signal.get("type", "")
    
    if "linkedin" in source.lower():
        reactions = engagement.get("reactions", 0)
        comments = engagement.get("comments", 0)
        return f"LinkedIn: {reactions} reactions, {comments} comments"
    elif "twitter" in source.lower():
        likes = engagement.get("likes", 0)
        retweets = engagement.get("retweets", 0)
        return f"Twitter: {likes} likes, {retweets} retweets"
    elif "reddit" in source.lower():
        score = engagement.get("score", 0)
        comments = engagement.get("comments", 0)
        return f"Reddit: {score} upvotes, {comments} comments"
    else:
        return "N/A (news source)"


async def score_signal_with_openai(
    signal: Dict[str, Any],
    client: AsyncOpenAI,
    themes: str,
    feedback_context: str = ""
) -> Dict[str, Any]:
    """Score a single signal using OpenAI gpt-5-nano — ICP interest litmus test."""

    content = get_signal_content(signal)

    user_prompt = SCORING_PROMPT.format(
        source=signal.get("collection_source", signal.get("type", "unknown")),
        title=signal.get("title", "")[:200],
        content=content,
        url=signal.get("url", ""),
        feedback_context=feedback_context
    )
    
    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a signal scoring assistant. Score signals on whether they are marketing/AI news that would interest a VP Marketing, CEO, or CMO at a mid-market company. Always respond with valid JSON only, no markdown."
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=2048
        )
        
        # Parse JSON response
        response_text = response.choices[0].message.content.strip()
        
        # Clean up response if it has markdown code blocks
        if response_text.startswith("```"):
            response_text = re.sub(r'^```json?\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)
        
        scores = json.loads(response_text)
        
        # Calculate weighted total score
        total_score = (
            scores.get("icp_interest", 0) * SCORING_WEIGHTS["icp_interest"] +
            scores.get("timeliness", 0) * SCORING_WEIGHTS["timeliness"] +
            scores.get("news_quality", 0) * SCORING_WEIGHTS["news_quality"]
        )
        
        return {
            "signal_id": signal.get("id", ""),
            "total_score": round(total_score, 1),
            "scores": {
                "icp_interest": scores.get("icp_interest", 0),
                "timeliness": scores.get("timeliness", 0),
                "news_quality": scores.get("news_quality", 0),
            },
            "news_type": scores.get("news_type", "other"),
            "news_summary": scores.get("news_summary", ""),
            "error": None
        }
    
    except json.JSONDecodeError as e:
        # Fall back to keyword scoring
        return score_signal_with_keywords(signal, f"JSON parse error: {str(e)[:50]}")
    except Exception as e:
        error_msg = str(e)[:100]
        # Check if rate limited
        if "429" in error_msg or "rate" in error_msg.lower() or "quota" in error_msg.lower():
            return score_signal_with_keywords(signal, "API rate limited - using keyword fallback")
        return score_signal_with_keywords(signal, f"API error: {error_msg[:50]}")


# ============== Keyword-Based Fallback Scoring ==============

# News indicator keywords (signals that this is actual news)
NEWS_KEYWORDS = {
    "high": [  # Strong news indicators - score 85-100
        "raised", "funding", "series a", "series b", "series c", "series d",
        "acquired", "acquisition", "merger", "ipo", "goes public",
        "announced", "launches", "launched", "unveils", "unveiled", "introduces",
        "reports", "reported", "study finds", "research shows", "survey reveals",
        "data shows", "according to", "new report", "latest report",
        "billion", "million", "valuation", "market cap",
        "appoints", "hires", "names", "promoted", "steps down", "resigns",
        "partnership", "partners with", "collaborates", "integrates",
        "regulation", "regulatory", "compliance", "law", "legislation",
        "breaking", "just in", "exclusive", "first look"
    ],
    "medium": [  # Moderate news indicators - score 60-84
        "trend", "trending", "growing", "growth", "decline", "rising",
        "update", "updates", "changes", "changing", "shift", "shifting",
        "2024", "2025", "2026", "q1", "q2", "q3", "q4", "quarterly",
        "year over year", "yoy", "month over month", "mom",
        "percent", "%", "increase", "decrease", "doubled", "tripled",
        "benchmark", "statistics", "metrics", "insights",
        "conference", "summit", "event", "webinar"
    ],
    "low": [  # Weak/no news indicators - score 0-59
        "i think", "in my opinion", "here's why", "here are", 
        "tips", "advice", "how to", "guide", "best practices",
        "should", "must", "need to", "you need",
        "hiring", "we're hiring", "job", "opportunity", "looking for",
        "thoughts on", "what do you think", "agree or disagree"
    ]
}

# Marketing relevance keywords
MARKETING_KEYWORDS = {
    "high": [  # Core marketing - score 80-100
        "marketing", "marketer", "cmo", "chief marketing",
        "martech", "marketing technology", "marketing automation",
        "campaign", "advertising", "ad spend", "media buy",
        "attribution", "measurement", "analytics", "roi",
        "brand", "branding", "awareness", "consideration",
        "content marketing", "social media marketing", "email marketing",
        "seo", "sem", "ppc", "paid media", "organic",
        "demand gen", "lead gen", "pipeline", "funnel",
        "agency", "agencies", "fractional cmo", "fractional marketing"
    ],
    "medium": [  # Adjacent to marketing - score 50-79
        "growth", "acquisition", "retention", "engagement",
        "customer", "audience", "segment", "targeting",
        "ai", "artificial intelligence", "machine learning", "automation",
        "saas", "b2b", "b2c", "enterprise", "startup",
        "strategy", "strategic", "planning", "execution"
    ]
}

# Company relevance keywords (MH-1 specific)
COMPANY_KEYWORDS = {
    "high": [  # Directly relevant to MH-1 - score 80-100
        "fractional cmo", "fractional marketing", "fractional",
        "agency alternative", "agency disruption", "agency model",
        "marketing talent", "marketing team", "marketing leadership",
        "ai marketing", "ai-powered marketing", "marketing ai",
        "mid-market", "growth stage", "series a", "series b",
        "marketing system", "full-stack marketing", "integrated marketing",
        "marketerhire", "mh-1"
    ],
    "medium": [  # Generally relevant - score 50-79
        "outsourced marketing", "marketing consultant", "marketing partner",
        "marketing ops", "marketing operations", "revenue marketing",
        "growth marketing", "performance marketing",
        "marketing budget", "marketing spend", "marketing investment",
        "cmo tenure", "marketing leadership", "vp marketing"
    ]
}


def score_signal_with_keywords(signal: Dict[str, Any], fallback_reason: str = "") -> Dict[str, Any]:
    """
    Deterministic keyword-based scoring as fallback.
    Litmus test: Is this marketing/AI news an ICP would care about?
    """
    
    # Combine title and content for analysis
    title = signal.get("title", "").lower()
    content = signal.get("content", "").lower()
    text = f"{title} {content}"
    
    # ---- ICP INTEREST (0-100) — Would a VP Marketing / CEO / CMO care? ----
    icp_score = 20  # Default low
    
    # Highest: directly about MH-1's core ICP topics
    for keyword in COMPANY_KEYWORDS["high"]:
        if keyword in text:
            icp_score = max(icp_score, 88)
            break
    
    if icp_score < 88:
        for keyword in COMPANY_KEYWORDS["medium"]:
            if keyword in text:
                icp_score = max(icp_score, 72)
                break
    
    # Marketing keywords are strong ICP-interest signals
    if icp_score < 88:
        for keyword in MARKETING_KEYWORDS["high"]:
            if keyword in text:
                icp_score = max(icp_score, 80)
                break
    
    if icp_score < 72:
        for keyword in MARKETING_KEYWORDS["medium"]:
            if keyword in text:
                icp_score = max(icp_score, 58)
                break
    
    # Penalize things ICPs don't care about
    anti_icp = ["job posting", "we're hiring", "looking for candidates", "apply now",
                "motivational", "grind", "hustle", "crypto", "web3", "nft"]
    for keyword in anti_icp:
        if keyword in text:
            icp_score = min(icp_score, 15)
            break
    
    # ---- TIMELINESS (0-100) — How recent is this? ----
    timeliness_score = 40  # Default low-mid
    
    very_recent = ["today", "yesterday", "just now", "breaking", "hours ago"]
    recent = ["this week", "just", "2026", "march 2026", "feb 2026", "january 2026"]
    
    for indicator in very_recent:
        if indicator in text:
            timeliness_score = 90
            break
    
    if timeliness_score < 90:
        for indicator in recent:
            if indicator in text:
                timeliness_score = max(timeliness_score, 75)
                break
    
    # Source-based timeliness boost
    source = signal.get("collection_source", "").lower()
    if "perplexity" in source:
        timeliness_score = max(timeliness_score, 70)
    elif "rss" in source:
        timeliness_score = max(timeliness_score, 65)
    elif "twitter" in source:
        timeliness_score = max(timeliness_score, 65)
    
    # ---- NEWS QUALITY (0-100) — Is this real news with substance? ----
    news_quality_score = 40  # Default
    news_type = "unknown"
    
    for keyword in NEWS_KEYWORDS["high"]:
        if keyword in text:
            news_quality_score = max(news_quality_score, 85)
            if any(k in keyword for k in ["raised", "funding", "series", "valuation", "billion", "million"]):
                news_type = "funding"
            elif any(k in keyword for k in ["launch", "unveil", "introduce", "announced"]):
                news_type = "product_launch"
            elif any(k in keyword for k in ["study", "research", "report", "data", "survey"]):
                news_type = "research_data"
            elif any(k in keyword for k in ["appoint", "hire", "name", "promoted", "resign"]):
                news_type = "executive_move"
            elif any(k in keyword for k in ["acqui", "merger", "ipo"]):
                news_type = "market_report"
            elif any(k in keyword for k in ["regulat", "compliance", "law"]):
                news_type = "regulatory"
            else:
                news_type = "industry_event"
            break
    
    if news_quality_score < 85:
        for keyword in NEWS_KEYWORDS["medium"]:
            if keyword in text:
                news_quality_score = max(news_quality_score, 65)
                if news_type == "unknown":
                    news_type = "market_report"
                break
    
    # Penalize opinion/advice content
    for keyword in NEWS_KEYWORDS["low"]:
        if keyword in text:
            news_quality_score = min(news_quality_score, 35)
            if "hiring" in keyword or "job" in keyword:
                news_type = "job_posting"
            else:
                news_type = "opinion"
            break
    
    # Calculate total weighted score
    total_score = (
        icp_score * SCORING_WEIGHTS["icp_interest"] +
        timeliness_score * SCORING_WEIGHTS["timeliness"] +
        news_quality_score * SCORING_WEIGHTS["news_quality"]
    )
    
    # Generate news summary
    if icp_score >= 70 and news_quality_score >= 60:
        news_summary = f"[Keyword match] Marketing/AI {news_type} — ICP-relevant"
    elif icp_score >= 50:
        news_summary = f"[Keyword match] Tangentially relevant {news_type}"
    else:
        news_summary = f"[Keyword match] Low ICP interest — {news_type}"
    
    if fallback_reason:
        news_summary = f"{fallback_reason}. {news_summary}"
    
    return {
        "signal_id": signal.get("id", ""),
        "total_score": round(total_score, 1),
        "scores": {
            "icp_interest": icp_score,
            "timeliness": timeliness_score,
            "news_quality": news_quality_score,
        },
        "news_type": news_type,
        "news_summary": news_summary,
        "error": "keyword_fallback",
        "scoring_method": "keyword"
    }


def emit_progress(completed: int, total: int, openai_count: int, keyword_count: int, errors: int, status: str = "running"):
    """Emit ranking progress as a JSON line to stdout so the frontend can read it.
    
    Uses os.write(1, ...) to bypass rich's Progress context manager which
    intercepts sys.stdout and wraps/splits long lines at terminal width.
    """
    try:
        line = "PROGRESS:" + json.dumps({
            "completed": completed,
            "total": total,
            "openai_count": openai_count,
            "keyword_count": keyword_count,
            "errors": errors,
            "status": status,
        }) + "\n"
        os.write(1, line.encode())
    except Exception:
        pass


async def rank_signals(
    signals: List[Dict[str, Any]],
    batch_size: int = 20,
    max_signals: Optional[int] = None,
    use_keywords: bool = False
) -> List[Dict[str, Any]]:
    """
    Rank all signals using OpenAI scoring with keyword fallback.
    
    Args:
        signals: List of signals to rank
        batch_size: Number of signals to process in parallel
        max_signals: Limit to top N signals
        use_keywords: Force keyword-only scoring (no OpenAI)
    """
    
    # Check if we should use keyword-only mode
    if use_keywords:
        console.print("[yellow]Using keyword-only scoring (OpenAI disabled)[/yellow]")
        client = None
    elif not OPENAI_API_KEY:
        console.print("[yellow]No OpenAI API key - using keyword-only scoring[/yellow]")
        use_keywords = True
        client = None
    else:
        # Initialize async OpenAI client
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    # Load themes and feedback for scoring
    themes = load_context()
    feedback_ctx = load_feedback_context()

    # Limit signals if specified
    if max_signals:
        signals = signals[:max_signals]
    
    scoring_method = "keyword" if use_keywords else f"OpenAI ({OPENAI_MODEL}) + keyword fallback"
    
    console.print(Panel(
        f'[bold cyan]Signal Ranking System[/bold cyan]\n\n'
        f'Signals to rank: {len(signals)}\n'
        f'Scoring: {scoring_method}\n'
        f'Batch size: {batch_size}',
        border_style='cyan'
    ))
    
    ranked_signals = []
    openai_count = 0
    keyword_count = 0
    errors = 0
    total = len(signals)
    completed_count = 0
    
    # Emit initial progress immediately so frontend sees it
    emit_progress(0, total, 0, 0, 0, "running")
    
    async def _score_one(signal: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Score a single signal and return (signal, result)."""
        if use_keywords:
            return signal, score_signal_with_keywords(signal)
        try:
            result = await score_signal_with_openai(signal, client, themes, feedback_ctx)
            return signal, result
        except Exception as e:
            return signal, score_signal_with_keywords(signal, f"Exception: {str(e)[:50]}")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Scoring signals...", total=total)
        
        # Process in batches but stream results as they arrive
        for i in range(0, total, batch_size):
            batch = signals[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total + batch_size - 1) // batch_size
            
            console.print(f"[dim]Batch {batch_num}/{total_batches} — processing {len(batch)} signals...[/dim]")
            
            # Create tasks for the batch
            coros = [_score_one(signal) for signal in batch]
            
            # Stream results as each completes (not waiting for whole batch)
            for future in asyncio.as_completed(coros):
                signal, result = await future
                
                if isinstance(result, Exception):
                    result = score_signal_with_keywords(signal, f"Exception: {str(result)[:50]}")
                    keyword_count += 1
                    errors += 1
                elif result.get("scoring_method") == "keyword":
                    keyword_count += 1
                    if result.get("error") and result.get("error") != "keyword_fallback":
                        errors += 1
                else:
                    openai_count += 1
                    if result.get("error"):
                        errors += 1
                
                ranked_signal = {**signal, "ranking": result}
                ranked_signals.append(ranked_signal)
                completed_count += 1
                progress.update(task, advance=1)
                
                # Emit progress on every signal for real-time UI updates
                emit_progress(completed_count, total, openai_count, keyword_count, errors, "running")
            
            console.print(f"[green]  ✓ Batch {batch_num} done — {completed_count}/{total} scored (OpenAI: {openai_count}, Keyword: {keyword_count}, Errors: {errors})[/green]")
            
            # Small delay between batches to avoid rate limits
            if i + batch_size < total:
                await asyncio.sleep(0.2)
    
    # Sort by total score (highest first)
    ranked_signals.sort(
        key=lambda x: x.get("ranking", {}).get("total_score", 0),
        reverse=True
    )
    
    # Emit final progress
    emit_progress(total, total, openai_count, keyword_count, errors, "complete")
    
    # Print scoring method summary
    console.print(f"\n[dim]Scoring breakdown:[/dim]")
    if openai_count > 0:
        console.print(f"  [green]✓ OpenAI ({OPENAI_MODEL}): {openai_count}[/green]")
    if keyword_count > 0:
        console.print(f"  [yellow]⚡ Keyword fallback: {keyword_count}[/yellow]")
    if errors > 0:
        console.print(f"  [red]⚠️ Errors: {errors}[/red]")
    
    return ranked_signals


def print_summary(ranked_signals: List[Dict[str, Any]], min_score: int = 0):
    """Print ranking summary."""
    
    # Filter by min score
    filtered = [s for s in ranked_signals if s.get("ranking", {}).get("total_score", 0) >= min_score]
    
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    console.print(f"[bold green]✅ RANKING COMPLETE[/bold green]")
    console.print(f"[bold green]{'='*60}[/bold green]\n")
    
    console.print(f"📊 Total Ranked: [bold]{len(ranked_signals)}[/bold]")
    console.print(f"📈 Above {min_score} score: [bold]{len(filtered)}[/bold]\n")
    
    # Score distribution
    score_buckets = {"90+": 0, "70-89": 0, "50-69": 0, "30-49": 0, "<30": 0}
    for s in ranked_signals:
        score = s.get("ranking", {}).get("total_score", 0)
        if score >= 90:
            score_buckets["90+"] += 1
        elif score >= 70:
            score_buckets["70-89"] += 1
        elif score >= 50:
            score_buckets["50-69"] += 1
        elif score >= 30:
            score_buckets["30-49"] += 1
        else:
            score_buckets["<30"] += 1
    
    dist_table = Table(title="Score Distribution", show_header=True, header_style="bold magenta")
    dist_table.add_column("Score Range", width=15)
    dist_table.add_column("Count", width=10, justify="right")
    dist_table.add_column("Quality", width=20)
    
    dist_table.add_row("90+", str(score_buckets["90+"]), "[green]Excellent[/green]")
    dist_table.add_row("70-89", str(score_buckets["70-89"]), "[cyan]High Quality[/cyan]")
    dist_table.add_row("50-69", str(score_buckets["50-69"]), "[yellow]Moderate[/yellow]")
    dist_table.add_row("30-49", str(score_buckets["30-49"]), "[orange3]Low[/orange3]")
    dist_table.add_row("<30", str(score_buckets["<30"]), "[red]Skip[/red]")
    
    console.print(dist_table)
    
    # Top signals table
    console.print("\n[bold]Top 10 Signals:[/bold]\n")
    
    top_table = Table(show_header=True, header_style="bold magenta")
    top_table.add_column("#", width=3, justify="right")
    top_table.add_column("Score", width=6, justify="center")
    top_table.add_column("Type", width=12)
    top_table.add_column("Source", width=10)
    top_table.add_column("Title", width=45)
    
    for i, signal in enumerate(filtered[:10], 1):
        ranking = signal.get("ranking", {})
        score = ranking.get("total_score", 0)
        source = signal.get("collection_source", signal.get("type", ""))[:10]
        title = signal.get("title", "")[:43] + "..."
        news_type = ranking.get("news_type", "other")[:12]
        
        # Color code score
        if score >= 70:
            score_str = f"[green]{score}[/green]"
        elif score >= 50:
            score_str = f"[yellow]{score}[/yellow]"
        else:
            score_str = f"[red]{score}[/red]"
        
        top_table.add_row(str(i), score_str, news_type, source, title)
    
    console.print(top_table)
    
    # Show news summaries for top 5
    console.print("\n[bold]Top 5 News Summaries:[/bold]\n")
    
    for i, signal in enumerate(filtered[:5], 1):
        ranking = signal.get("ranking", {})
        score = ranking.get("total_score", 0)
        title = signal.get("title", "")[:60]
        news_type = ranking.get("news_type", "other")
        news_summary = ranking.get("news_summary", "")
        
        console.print(f"[magenta]{i}. [{score}] {title}...[/magenta]")
        console.print(f"   [cyan]Type: {news_type}[/cyan]")
        console.print(f"   [dim]{news_summary}[/dim]")
        console.print()


def output_json(ranked_signals: List[Dict[str, Any]], min_score: int = 0):
    """Output ranked signals as JSON."""
    filtered = [s for s in ranked_signals if s.get("ranking", {}).get("total_score", 0) >= min_score]
    
    output = {
        "ranked_at": datetime.now().isoformat(),
        "total_signals": len(ranked_signals),
        "filtered_count": len(filtered),
        "min_score_filter": min_score,
        "scoring_weights": SCORING_WEIGHTS,
        "signals": filtered
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


SIGNALS_FILE = "outputs/signals.json"


def save_to_file(ranked_signals: List[Dict[str, Any]], min_score: int = 0, filename: str = None):
    """Merge rankings back into signals.json (in-place update)."""
    filename = filename or SIGNALS_FILE
    
    Path("outputs").mkdir(exist_ok=True)
    
    # Build a lookup of ranking data by signal id
    ranking_by_id = {}
    for sig in ranked_signals:
        sid = sig.get("id", "")
        if sid:
            ranking_by_id[sid] = sig.get("ranking")
    
    # Load existing signals.json and merge ranking into each signal
    existing_data = {}
    if Path(filename).exists():
        with open(filename, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    
    existing_signals = existing_data.get("signals", [])
    
    for sig in existing_signals:
        sid = sig.get("id", "")
        if sid in ranking_by_id:
            sig["ranking"] = ranking_by_id[sid]
    
    # Sort by score (highest first)
    existing_signals.sort(
        key=lambda x: x.get("ranking", {}).get("total_score", 0),
        reverse=True
    )
    
    # Add ranking metadata
    existing_data["signals"] = existing_signals
    existing_data["ranked_at"] = datetime.now().isoformat()
    existing_data["scoring_weights"] = SCORING_WEIGHTS
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[green]💾 Merged rankings into: {filename} ({len(ranking_by_id)} signals scored)[/green]")
    return filename


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description='Rank signals using OpenAI gpt-4.1-nano based on MH-1 content criteria'
    )
    parser.add_argument('input_file', type=str, nargs='?', default=SIGNALS_FILE,
                       help='Path to signals JSON file (default: outputs/signals.json)')
    parser.add_argument('--min-score', type=int, default=0,
                       help='Minimum score to include in output (default: 0)')
    parser.add_argument('--top', type=int, default=None,
                       help='Only rank top N signals (by engagement) to save API costs')
    parser.add_argument('--batch-size', type=int, default=20,
                       help='Batch size for API calls (default: 20)')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON to stdout')
    parser.add_argument('--save', action='store_true',
                       help='Save to file in outputs/')
    parser.add_argument('--keywords', action='store_true',
                       help='Use keyword-only scoring (no OpenAI API calls)')
    
    args = parser.parse_args()
    
    # Check input file exists
    if not Path(args.input_file).exists():
        console.print(f"[red]Error: File not found: {args.input_file}[/red]")
        sys.exit(1)
    
    # Check API key (warn but don't exit - keyword fallback works without it)
    if not OPENAI_API_KEY and not args.keywords:
        console.print("[yellow]Warning: OPENAI_KEY not set in .env - will use keyword-only scoring[/yellow]")
    
    # Load signals
    console.print(f"[dim]Loading signals from: {args.input_file}[/dim]")
    signals = load_signals(args.input_file)
    
    if not signals:
        console.print("[red]Error: No signals found in file[/red]")
        sys.exit(1)
    
    console.print(f"[dim]Found {len(signals)} signals[/dim]")
    
    # Rank signals
    ranked_signals = await rank_signals(
        signals=signals,
        batch_size=args.batch_size,
        max_signals=args.top,
        use_keywords=args.keywords
    )
    
    # Output
    if args.json:
        output_json(ranked_signals, args.min_score)
    else:
        print_summary(ranked_signals, args.min_score)
        
        if args.save:
            save_to_file(ranked_signals, args.min_score)


if __name__ == "__main__":
    asyncio.run(main())

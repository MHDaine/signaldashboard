"""Research service for parallel signal discovery."""

import asyncio
import re
import time
from typing import List, Optional, Tuple
from uuid import uuid4
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..models import (
    Signal, SignalMetadata, SignalCategory, SignalStatus,
    ResearchResponse
)
from ..providers import (
    PerplexityProvider, GeminiProvider,
    LinkedInProvider, RedditProvider, TwitterProvider,
    RawSignal
)
from ..context_loader import context_loader
from .signal_store import signal_store

console = Console()


class ResearchService:
    """Service for conducting parallel deep research."""
    
    def __init__(self):
        # Core AI research providers
        self.ai_providers = [
            PerplexityProvider(),
            GeminiProvider(),
        ]
        
        # Social media providers
        self.social_providers = [
            LinkedInProvider(),
            RedditProvider(),
            TwitterProvider(),
        ]
        
        # Default: AI providers only
        self.providers = self.ai_providers
    
    async def execute_research(
        self,
        context_path: str,
        custom_queries: Optional[List[str]] = None,
        max_signals: int = 50,
        include_social: bool = False,
    ) -> ResearchResponse:
        """Execute deep research across all providers in parallel."""
        start_time = time.time()
        
        console.print("\n[bold cyan]🔬 Starting Deep Research...[/bold cyan]\n")
        
        # Load context
        context = context_loader.load(context_path)
        context_summary = context_loader.get_summary()
        
        # Use custom queries or auto-generated ones
        queries = custom_queries if custom_queries else context.search_queries[:10]
        
        # Select providers based on include_social flag
        active_providers = self.providers
        if include_social:
            active_providers = self.ai_providers + self.social_providers
        
        console.print(f"[dim]Running {len(queries)} queries across {len(active_providers)} providers[/dim]\n")
        
        # Create all search tasks
        tasks: List[Tuple[str, asyncio.Task]] = []
        for query in queries:
            for provider in active_providers:
                task = asyncio.create_task(
                    provider.search_with_timeout(query, context_summary)
                )
                tasks.append((f"{provider.source_name}:{query[:30]}", task))
        
        # Execute all tasks in parallel
        console.print(f"[yellow]⚡ Executing {len(tasks)} parallel searches...[/yellow]")
        
        results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        
        # Collect raw signals
        raw_signals: List[Tuple[RawSignal, str, str]] = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                console.print(f"[red]❌ Task failed: {result}[/red]")
                continue
            
            for signal in result.signals:
                raw_signals.append((signal, result.source, result.query))
        
        console.print(f"[green]✓ Collected {len(raw_signals)} raw signals[/green]")
        
        # Deduplicate
        deduped = self._deduplicate(raw_signals)
        console.print(f"[green]✓ After deduplication: {len(deduped)} signals[/green]")
        
        # Convert to Signal objects with ranking
        signals = [
            self._create_signal(raw, source, query, context_summary)
            for raw, source, query in deduped
        ]
        
        # Sort by relevance and limit
        signals.sort(key=lambda s: s.relevance_score, reverse=True)
        signals = signals[:max_signals]
        
        # Store signals
        signal_store.add_many(signals)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        console.print(f"\n[bold green]✅ Research complete![/bold green]")
        console.print(f"[dim]   Found {len(signals)} signals in {duration_ms}ms[/dim]\n")
        
        return ResearchResponse(
            signals=signals,
            total_found=len(signals),
            search_duration_ms=duration_ms,
            sources=[p.source_name for p in active_providers],
            query_count=len(queries)
        )
    
    def _deduplicate(
        self, 
        signals: List[Tuple[RawSignal, str, str]]
    ) -> List[Tuple[RawSignal, str, str]]:
        """Deduplicate signals based on title similarity."""
        seen: dict = {}
        
        for item in signals:
            raw, source, query = item
            # Normalize title for comparison
            key = re.sub(r'\[.*?\]', '', raw.title.lower()).strip()[:50]
            
            if key not in seen or raw.confidence > seen[key][0].confidence:
                seen[key] = item
        
        return list(seen.values())
    
    def _create_signal(
        self,
        raw: RawSignal,
        source: str,
        query: str,
        context_summary: str
    ) -> Signal:
        """Convert raw signal to full Signal with ranking."""
        return Signal(
            id=str(uuid4()),
            title=re.sub(r'^\[.*?\]\s*', '', raw.title),  # Remove source prefix
            summary=raw.summary,
            content=raw.content,
            category=self._categorize(raw, query),
            relevance_score=self._calculate_relevance(raw, context_summary),
            metadata=SignalMetadata(
                source=source,
                source_url=raw.source_url,
                fetched_at=datetime.now(),
                confidence=raw.confidence,
                query=query
            ),
            status=SignalStatus.PENDING,
            tags=self._generate_tags(raw, query),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    def _categorize(self, raw: RawSignal, query: str) -> SignalCategory:
        """Categorize a signal based on content."""
        content = f"{raw.title} {raw.summary} {query}".lower()
        
        if any(term in content for term in ['competitor', 'rival', 'growtal', 'mayple']):
            return SignalCategory.COMPETITOR_MOVE
        if any(term in content for term in ['ai', 'automation', 'technology', 'tech']):
            return SignalCategory.TECHNOLOGY_UPDATE
        if any(term in content for term in ['trend', 'shift', 'change', 'evolution']):
            return SignalCategory.INDUSTRY_TREND
        if any(term in content for term in ['regulation', 'compliance', 'privacy', 'legal']):
            return SignalCategory.REGULATORY_CHANGE
        if any(term in content for term in ['customer', 'buyer', 'user', 'client']):
            return SignalCategory.CUSTOMER_INSIGHT
        if any(term in content for term in ['content', 'thought leadership', 'linkedin', 'publish']):
            return SignalCategory.CONTENT_OPPORTUNITY
        if any(term in content for term in ['partnership', 'integration', 'alliance']):
            return SignalCategory.PARTNERSHIP_OPPORTUNITY
        
        return SignalCategory.MARKET_SHIFT
    
    def _calculate_relevance(self, raw: RawSignal, context_summary: str) -> int:
        """Calculate relevance score (0-100)."""
        content = f"{raw.title} {raw.summary} {raw.content}".lower()
        
        score = int(raw.confidence * 40)  # Base score from confidence
        
        # Key term matching
        key_terms = [
            'ai marketing', 'marketing automation', 'agency', 'marketerhire', 'mh-1',
            'fractional cmo', 'b2b saas', 'fintech', 'ecommerce', 'dtc',
            'attribution', 'talent', 'workflow', 'enterprise', 'mid-market',
            'content', 'thought leadership', 'linkedin'
        ]
        
        for term in key_terms:
            if term in content:
                score += 5
        
        # Data/statistics boost
        if re.search(r'\d+%', raw.content):
            score += 5
        if re.search(r'\$[\d,]+', raw.content):
            score += 5
        
        # Recency boost
        if any(term in content for term in ['2026', 'recent', 'new', 'latest']):
            score += 5
        
        # Actionability boost
        if any(term in content for term in ['opportunity', 'should', 'recommend', 'action']):
            score += 5
        
        return min(score, 100)
    
    def _generate_tags(self, raw: RawSignal, query: str) -> List[str]:
        """Generate tags for a signal."""
        tags = []
        content = f"{raw.title} {raw.summary}".lower()
        
        tag_mappings = {
            'ai': 'AI',
            'marketing': 'Marketing',
            'b2b': 'B2B',
            'saas': 'SaaS',
            'content': 'Content',
            'linkedin': 'LinkedIn',
            'attribution': 'Attribution',
            'agency': 'Agency',
            'cmo': 'Executive',
            'executive': 'Executive',
            'trend': 'Trend',
        }
        
        for keyword, tag in tag_mappings.items():
            if keyword in content:
                tags.append(tag)
        
        # Add Data tag if statistics present
        if re.search(r'\d+%', content):
            tags.append('Data')
        
        return list(set(tags))[:5]


# Global instance
research_service = ResearchService()


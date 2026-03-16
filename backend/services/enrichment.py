"""Enrichment service for deep signal analysis."""

import asyncio
import httpx
import json
import re
from typing import List, Optional
from datetime import datetime
from rich.console import Console

from ..models import (
    Signal, EnrichedSignal, SignalEnrichment, 
    MarketImpact, FounderRelevance
)
from ..config import settings
from ..context_loader import context_loader
from .signal_store import signal_store

console = Console()


class EnrichmentService:
    """Service for enriching signals with deep analysis."""
    
    async def enrich_signals(
        self,
        signal_ids: List[str],
        depth: str = "standard"
    ) -> List[EnrichedSignal]:
        """Enrich multiple signals."""
        console.print(f"\n[bold cyan]🔬 Enriching {len(signal_ids)} signals...[/bold cyan]\n")
        
        tasks = [
            self._enrich_single(signal_id, depth)
            for signal_id in signal_ids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        enriched = []
        for result in results:
            if isinstance(result, EnrichedSignal):
                enriched.append(result)
                signal_store.add_enriched(result)
        
        console.print(f"[green]✅ Enriched {len(enriched)} signals[/green]\n")
        return enriched
    
    async def enrich_all_approved(self) -> List[EnrichedSignal]:
        """Enrich all approved signals."""
        approved = signal_store.get_by_status("approved")
        return await self.enrich_signals([s.id for s in approved])
    
    async def _enrich_single(
        self, 
        signal_id: str, 
        depth: str
    ) -> Optional[EnrichedSignal]:
        """Enrich a single signal."""
        signal = signal_store.get(signal_id)
        if not signal:
            console.print(f"[yellow]⚠️ Signal not found: {signal_id}[/yellow]")
            return None
        
        context_summary = context_loader.get_summary()
        
        # Try Perplexity for deep research enrichment
        perplexity_key = settings.perplexity_api_key
        if perplexity_key:
            enrichment = await self._enrich_with_perplexity(signal, context_summary)
        else:
            enrichment = self._generate_mock_enrichment(signal)
        
        return EnrichedSignal(
            **signal.model_dump(),
            enrichment=enrichment,
            enriched_at=datetime.now()
        )
    
    async def _enrich_with_perplexity(
        self, 
        signal: Signal, 
        context: str
    ) -> SignalEnrichment:
        """Use Perplexity for deep research enrichment."""
        try:
            async with httpx.AsyncClient() as client:
                # First call: Deep research on the signal topic
                research_response = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.perplexity_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar-pro",  # Deep research model
                        "messages": [
                            {
                                "role": "system",
                                "content": f"""You are a strategic analyst doing deep research for MH-1, an AI-native marketing company.

Context about MH-1:
{context}

Your task is to provide comprehensive research and strategic analysis."""
                            },
                            {
                                "role": "user",
                                "content": f"""Research this market signal deeply and provide strategic analysis:

Signal Title: {signal.title}
Signal Summary: {signal.summary}
Signal Content: {signal.content}

Provide your analysis in JSON format:
{{
  "deep_dive": "A comprehensive 2-3 paragraph analysis with specific data points and sources",
  "key_insights": ["insight1 with data", "insight2 with data", "insight3 with data"],
  "actionable_recommendations": ["specific action 1", "specific action 2", "specific action 3"],
  "related_topics": ["topic1", "topic2", "topic3"],
  "market_impact": {{
    "short_term": "Impact in next 3-6 months with specific predictions",
    "long_term": "Impact in 1-2 years with trend analysis",
    "risk_level": "low|medium|high",
    "opportunity_level": "low|medium|high"
  }},
  "founder_relevance": [
    {{
      "founder_name": "Chris Toy",
      "pillar_name": "AI as Marketing Superpower",
      "relevance_reason": "Why relevant to this founder",
      "content_angle": "Specific content angle with talking points"
    }}
  ]
}}

Return only valid JSON."""
                            }
                        ],
                        "temperature": 0.2,
                        "max_tokens": 2000,
                    },
                    timeout=60.0
                )
                
                data = research_response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                citations = data.get("citations", [])
                
                # Extract JSON from response
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    enrichment_data = json.loads(json_match.group())
                    
                    console.print(f"[green]✓ Perplexity enriched: {signal.title[:50]}...[/green]")
                    
                    return SignalEnrichment(
                        deep_dive=enrichment_data.get("deep_dive", ""),
                        key_insights=enrichment_data.get("key_insights", []),
                        actionable_recommendations=enrichment_data.get("actionable_recommendations", []),
                        related_topics=enrichment_data.get("related_topics", []),
                        sources=[{"url": url, "title": url.split("/")[-1] or "Source"} for url in citations[:5]],
                        market_impact=MarketImpact(
                            short_term=enrichment_data.get("market_impact", {}).get("short_term", ""),
                            long_term=enrichment_data.get("market_impact", {}).get("long_term", ""),
                            risk_level=enrichment_data.get("market_impact", {}).get("risk_level", "medium"),
                            opportunity_level=enrichment_data.get("market_impact", {}).get("opportunity_level", "medium"),
                        ),
                        founder_relevance=[
                            FounderRelevance(
                                founder_id=fr.get("founder_name", "").lower().replace(" ", "-"),
                                founder_name=fr.get("founder_name", ""),
                                pillar_id=fr.get("pillar_name", "").lower().replace(" ", "_"),
                                pillar_name=fr.get("pillar_name", ""),
                                relevance_reason=fr.get("relevance_reason", ""),
                                content_angle=fr.get("content_angle", ""),
                            )
                            for fr in enrichment_data.get("founder_relevance", [])
                        ]
                    )
        
        except Exception as e:
            console.print(f"[red]❌ Perplexity enrichment failed: {e}[/red]")
        
        return self._generate_mock_enrichment(signal)
    
    async def _enrich_with_gemini(
        self, 
        signal: Signal, 
        context: str
    ) -> SignalEnrichment:
        """Use Gemini for deep enrichment."""
        try:
            import google.generativeai as genai
            
            gemini_key = settings.effective_gemini_key
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            prompt = f"""You are a strategic analyst for MH-1, an AI-native marketing company.

Context about MH-1:
{context}

Analyze this market signal and provide strategic enrichment:

Signal Title: {signal.title}
Signal Summary: {signal.summary}
Signal Content: {signal.content}
Category: {signal.category}

Provide your analysis in the following JSON format:
{{
  "deep_dive": "A 2-3 paragraph deep analysis of this signal's implications",
  "key_insights": ["insight1", "insight2", "insight3"],
  "actionable_recommendations": ["recommendation1", "recommendation2", "recommendation3"],
  "related_topics": ["topic1", "topic2", "topic3"],
  "market_impact": {{
    "short_term": "Impact in next 3-6 months",
    "long_term": "Impact in 1-2 years",
    "risk_level": "low|medium|high",
    "opportunity_level": "low|medium|high"
  }},
  "founder_relevance": [
    {{
      "founder_name": "Chris Toy or Raaja Nemani or Cameron Rzonca or Nikhil Arora or Aneesha Rao",
      "pillar_name": "Relevant content pillar name",
      "relevance_reason": "Why this signal is relevant to this founder's expertise",
      "content_angle": "Suggested content angle or talking point"
    }}
  ]
}}

Return only valid JSON."""
            
            response = await model.generate_content_async(prompt)
            text = response.text
            
            # Extract JSON
            import json
            import re
            
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                
                return SignalEnrichment(
                    deep_dive=data.get("deep_dive", ""),
                    key_insights=data.get("key_insights", []),
                    actionable_recommendations=data.get("actionable_recommendations", []),
                    related_topics=data.get("related_topics", []),
                    sources=[],
                    market_impact=MarketImpact(
                        short_term=data.get("market_impact", {}).get("short_term", ""),
                        long_term=data.get("market_impact", {}).get("long_term", ""),
                        risk_level=data.get("market_impact", {}).get("risk_level", "medium"),
                        opportunity_level=data.get("market_impact", {}).get("opportunity_level", "medium"),
                    ),
                    founder_relevance=[
                        FounderRelevance(
                            founder_id=fr.get("founder_name", "").lower().replace(" ", "-"),
                            founder_name=fr.get("founder_name", ""),
                            pillar_id=fr.get("pillar_name", "").lower().replace(" ", "_"),
                            pillar_name=fr.get("pillar_name", ""),
                            relevance_reason=fr.get("relevance_reason", ""),
                            content_angle=fr.get("content_angle", ""),
                        )
                        for fr in data.get("founder_relevance", [])
                    ]
                )
        
        except Exception as e:
            console.print(f"[red]❌ Gemini enrichment failed: {e}[/red]")
        
        return self._generate_mock_enrichment(signal)
    
    def _generate_mock_enrichment(self, signal: Signal) -> SignalEnrichment:
        """Generate mock enrichment data."""
        is_ai_related = 'AI' in signal.tags or signal.category == 'technology_update'
        is_competitor = signal.category == 'competitor_move'
        is_content = signal.category == 'content_opportunity'
        
        return SignalEnrichment(
            deep_dive=f"""This signal represents a significant development in the {signal.category.replace('_', ' ')} space. {signal.summary}

For MH-1, this presents both opportunities and considerations. The trend aligns with the company's positioning as a "Full-Stack Human + AI Marketing System" and could be leveraged in thought leadership content.

Strategic implications include potential competitive advantages in positioning against traditional agencies and talent marketplaces.""",
            key_insights=[
                "This trend validates MH-1's focus on AI-native marketing systems",
                "Market timing appears favorable for aggressive content positioning",
                "Competitors are likely to respond within 3-6 months",
            ],
            actionable_recommendations=[
                "Create thought leadership content addressing this signal within 2 weeks",
                "Update sales enablement materials to reference this trend",
                "Consider a webinar or LinkedIn Live on the topic",
            ],
            related_topics=[
                "AI Marketing Automation",
                "Marketing Attribution",
                "B2B Content Strategy",
            ],
            sources=[],
            market_impact=MarketImpact(
                short_term="Increased market awareness creates better top-of-funnel opportunities",
                long_term="Industry consolidation likely to accelerate, favoring established players",
                risk_level="medium" if is_competitor else "low",
                opportunity_level="high" if (is_ai_related or is_content) else "medium",
            ),
            founder_relevance=[
                FounderRelevance(
                    founder_id="chris-toy",
                    founder_name="Chris Toy",
                    pillar_id="ct_ai_superpower" if is_ai_related else "ct_fundamentals",
                    pillar_name="AI as Marketing Superpower" if is_ai_related else "Fundamentals Over Fads",
                    relevance_reason=f"This signal directly relates to Chris's perspective on {'AI integration in marketing' if is_ai_related else 'marketing fundamentals'}",
                    content_angle=f'"{signal.title}" - a perfect example of why {"AI systems beat AI tools" if is_ai_related else "fundamentals matter more than fads"}',
                ),
                FounderRelevance(
                    founder_id="cameron-rzonca",
                    founder_name="Cameron Rzonca",
                    pillar_id="cr_systems",
                    pillar_name="From AI Tools to AI Systems",
                    relevance_reason="Cameron can speak to the technical implications and system-level thinking required",
                    content_angle="How MH-1's integrated approach capitalizes on this market shift",
                ),
            ]
        )


# Global instance
enrichment_service = EnrichmentService()


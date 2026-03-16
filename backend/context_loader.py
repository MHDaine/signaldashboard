"""Context loading and parsing for Signal Collection."""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class FounderInfo:
    """Information about a founder."""
    id: str
    name: str
    role: str
    pillars: List[str] = field(default_factory=list)
    pov_statements: List[str] = field(default_factory=list)


@dataclass
class ParsedContext:
    """Parsed context data."""
    company_profile: str = ""
    audience_personas: str = ""
    pov_and_pillars: str = ""
    competitors: str = ""
    tam_analysis: str = ""
    founders: List[FounderInfo] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)


class ContextLoader:
    """Loads and parses context from a folder."""
    
    def __init__(self):
        self._cache: Optional[ParsedContext] = None
        self._cache_path: Optional[str] = None
    
    def load(self, context_path: str) -> ParsedContext:
        """Load context from the specified path."""
        # Return cache if same path
        if self._cache and self._cache_path == context_path:
            return self._cache
        
        context = ParsedContext()
        path = Path(context_path)
        
        if not path.exists():
            raise ValueError(f"Context path does not exist: {context_path}")
        
        # Load company profile
        company_profile_path = path / "company-profile.md"
        if company_profile_path.exists():
            context.company_profile = company_profile_path.read_text()
        
        # Load audience personas
        audience_path = path / "audience-persona.md"
        if audience_path.exists():
            context.audience_personas = audience_path.read_text()
        
        # Load POV and pillars
        pov_path = path / "pov.md"
        if pov_path.exists():
            context.pov_and_pillars = pov_path.read_text()
        
        # Load competitor research
        competitor_path = path / "competitor-research.md"
        if competitor_path.exists():
            context.competitors = competitor_path.read_text()
        
        # Load TAM analysis
        tam_path = path / "tam-analysis.md"
        if tam_path.exists():
            context.tam_analysis = tam_path.read_text()
        
        # Load founder info
        founder_path = path / "founder-info"
        if founder_path.exists():
            for file in founder_path.glob("*-research.md"):
                content = file.read_text()
                founder_name = file.stem.replace("-research", "").replace("-", " ").title()
                context.founders.append(FounderInfo(
                    id=file.stem.replace("-research", ""),
                    name=founder_name,
                    role=self._extract_role(content),
                    pillars=self._extract_pillars(content),
                    pov_statements=self._extract_pov_statements(content),
                ))
        
        # Generate search queries
        context.search_queries = self._generate_search_queries(context)
        
        # Cache the result
        self._cache = context
        self._cache_path = context_path
        
        return context
    
    def get_summary(self) -> str:
        """Get a summary of the loaded context."""
        if not self._cache:
            return ""
        
        return """
Company: MH-1 by MarketerHire
Tagline: Full-Stack Human + AI Marketing System
Target: Mid-market, venture-backed companies ($10M-$100M ARR)
Price: $30,000/month
Key Differentiators:
- AI-native marketing system (not just tools)
- Unlimited automations
- Cancel anytime flexibility
- Top 1% verified expert talent

Target Personas:
- Growth-Stage VP of Marketing (vendor consolidation, AI strategy)
- Founder/CEO (marketing clarity, agency alternative)
- First-Time CMO (quick wins, transformation playbook)

Key Content Pillars:
- The Death of Attribution (Chris Toy)
- AI Tools vs AI Systems (Cameron Rzonca)
- P&L-Driven Growth (Nikhil Arora)
- Community as Competitive Moat (Raaja Nemani)
- Full-Stack Consumer Operator (Aneesha Rao)

Competitors: GrowTal, Mayple, Upwork, Marketri, Averi.ai
        """.strip()
    
    def clear_cache(self):
        """Clear the context cache."""
        self._cache = None
        self._cache_path = None
    
    def _extract_role(self, content: str) -> str:
        """Extract role from founder content."""
        match = re.search(r'\*\*Role\*\*:\s*(.+)', content, re.IGNORECASE)
        return match.group(1).strip() if match else "Team Member"
    
    def _extract_pillars(self, content: str) -> List[str]:
        """Extract content pillars from founder content."""
        pillars = []
        for match in re.finditer(r'#### Pillar \d+: (.+)', content):
            pillars.append(match.group(1).strip())
        return pillars
    
    def _extract_pov_statements(self, content: str) -> List[str]:
        """Extract POV statements from founder content."""
        statements = []
        for match in re.finditer(r'\*\*POV Statement:\*\*\s*>\s*"([^"]+)"', content):
            statements.append(match.group(1).strip())
        return statements
    
    def _generate_search_queries(self, context: ParsedContext) -> List[str]:
        """Generate news-focused search queries based on MH-1's POVs and audience."""
        queries = [
            # === RECENT NEWS: AI Marketing Industry ===
            "AI marketing news this week February 2026",
            "marketing automation industry announcements 2026",
            "AI marketing agency funding news latest",
            "enterprise AI marketing adoption statistics 2026",
            
            # === RECENT NEWS: B2B/SaaS (Target Audience) ===
            "B2B SaaS marketing news this month",
            "B2B marketing trends February 2026",
            "SaaS company marketing strategies news",
            "venture backed startup marketing news",
            
            # === CHRIS TOY POV: Death of Attribution ===
            "marketing attribution challenges news 2026",
            "privacy changes marketing impact latest news",
            "cookie deprecation marketing news update",
            "marketing measurement alternatives news",
            
            # === CAMERON RZONCA POV: AI Tools vs Systems ===
            "AI marketing tools vs platforms news",
            "marketing AI integration challenges news",
            "AI marketing workflow automation news 2026",
            "AI marketing ROI statistics latest",
            
            # === NIKHIL ARORA POV: P&L-Driven Growth ===
            "CMO accountability revenue news 2026",
            "marketing efficiency metrics news",
            "growth marketing ROI news latest",
            "marketing budget efficiency news 2026",
            
            # === RAAJA NEMANI POV: Community & Talent ===
            "fractional CMO market news 2026",
            "marketing talent shortage news",
            "freelance marketing trends news",
            "marketing agency consolidation news",
            
            # === ANEESHA RAO POV: DTC/Consumer ===
            "DTC ecommerce marketing news 2026",
            "consumer brand marketing trends news",
            "ecommerce marketing automation news",
            
            # === TARGET PERSONAS: Pain Points ===
            "VP marketing challenges news 2026",
            "first time CMO challenges news",
            "startup founder marketing struggles news",
            "marketing agency performance issues news",
            
            # === COMPETITIVE INTELLIGENCE ===
            "GrowTal news 2026",
            "Mayple marketing platform news",
            "marketing talent marketplace funding news",
            "AI marketing startups funding news 2026",
        ]
        
        return queries


# Global instance
context_loader = ContextLoader()


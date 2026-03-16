"""Base provider class for research providers."""

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from rich.console import Console

console = Console()


@dataclass
class RawSignal:
    """Raw signal data from a provider."""
    title: str
    summary: str
    content: str
    source_url: Optional[str] = None
    published_date: Optional[str] = None
    confidence: float = 0.7


@dataclass
class ProviderResult:
    """Result from a provider search."""
    signals: List[RawSignal]
    source: str
    query: str
    duration_ms: int
    error: Optional[str] = None
    citations: Optional[List[str]] = None  # Source URLs from provider


class BaseProvider(ABC):
    """Abstract base class for research providers."""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the provider source."""
        pass
    
    @abstractmethod
    async def search(self, query: str, context: str) -> ProviderResult:
        """Execute a search query."""
        pass
    
    async def search_with_timeout(
        self, 
        query: str, 
        context: str, 
        timeout: float = 30.0
    ) -> ProviderResult:
        """Execute search with timeout."""
        try:
            return await asyncio.wait_for(
                self.search(query, context),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            console.print(f"[yellow]⏱️ {self.source_name} timed out for query: {query[:50]}...[/yellow]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query=query,
                duration_ms=int(timeout * 1000),
                error="Request timeout"
            )
        except Exception as e:
            console.print(f"[red]❌ {self.source_name} error: {str(e)}[/red]")
            return ProviderResult(
                signals=[],
                source=self.source_name,
                query=query,
                duration_ms=0,
                error=str(e)
            )
    
    def parse_signals_from_text(self, text: str, query: str) -> List[RawSignal]:
        """Parse signals from unstructured text."""
        signals = []
        
        # Skip preamble patterns
        preamble_patterns = [
            r'^As a research analyst',
            r'^As your research analyst',
            r'^Here are \d+',
            r'^I understand',
            r'^MH-1,? here',
            r'^Given the',
            r'^Based on',
            r'^I\'ve simulated',
            r'^For MH-1',
        ]
        
        # Split by headers or numbered items
        sections = re.split(r'(?=#{1,3}\s|\d+\.\s*\*\*)', text)
        
        for section in sections:
            if len(section.strip()) < 50:
                continue
            
            # Skip preamble sections
            if any(re.match(pattern, section.strip(), re.IGNORECASE) for pattern in preamble_patterns):
                continue
            
            # Extract title
            title_match = re.match(r'^#{1,3}\s*(.+)|^\d+\.\s*\*\*(.+?)\*\*', section)
            title = (title_match.group(1) or title_match.group(2)).strip() if title_match else self._generate_title(section)
            
            # Clean up title (remove leading numbers, asterisks, quotes)
            title = re.sub(r'^[\d\.\*\s]+', '', title).strip()
            title = re.sub(r'^\*+|\*+$', '', title).strip()
            title = re.sub(r'^["\']|["\']$', '', title).strip()
            
            if len(title) < 10:
                continue
            
            summary = self._extract_summary(section)
            
            signals.append(RawSignal(
                title=title,
                summary=summary,
                content=section.strip(),
                confidence=self._calculate_confidence(section, query),
            ))
        
        return signals[:5]  # Max 5 signals per query
    
    def _generate_title(self, content: str) -> str:
        """Generate a title from content."""
        first_sentence = content.split('.')[0]
        return first_sentence[:100].strip()
    
    def _extract_summary(self, content: str) -> str:
        """Extract a summary from content."""
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 20]
        return '. '.join(sentences[:3])[:300] + '...' if sentences else content[:300]
    
    def _calculate_confidence(self, content: str, query: str) -> float:
        """Calculate confidence score based on content relevance."""
        query_terms = query.lower().split()
        content_lower = content.lower()
        
        # Count matching terms
        match_count = sum(1 for term in query_terms if len(term) > 3 and term in content_lower)
        match_ratio = match_count / len(query_terms) if query_terms else 0
        
        # Check for data indicators
        has_data = bool(re.search(r'\d+%|\$\d+|\d{4}', content))
        has_quote = '"' in content or '"' in content
        
        confidence = 0.5 + (match_ratio * 0.3)
        if has_data:
            confidence += 0.1
        if has_quote:
            confidence += 0.1
        
        return min(confidence, 1.0)


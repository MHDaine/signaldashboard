"""In-memory signal storage."""

from typing import Dict, List, Optional
from datetime import datetime
from ..models import Signal, EnrichedSignal, SignalStatus, Stats


class SignalStore:
    """In-memory storage for signals."""
    
    def __init__(self):
        self._signals: Dict[str, Signal] = {}
        self._enriched: Dict[str, EnrichedSignal] = {}
    
    def add(self, signal: Signal) -> None:
        """Add a signal to the store."""
        self._signals[signal.id] = signal
    
    def add_many(self, signals: List[Signal]) -> None:
        """Add multiple signals to the store."""
        for signal in signals:
            self.add(signal)
    
    def get(self, signal_id: str) -> Optional[Signal]:
        """Get a signal by ID."""
        return self._signals.get(signal_id)
    
    def get_all(self) -> List[Signal]:
        """Get all signals, sorted by relevance."""
        return sorted(
            self._signals.values(),
            key=lambda s: s.relevance_score,
            reverse=True
        )
    
    def get_by_status(self, status: SignalStatus) -> List[Signal]:
        """Get signals by status."""
        return [s for s in self.get_all() if s.status == status]
    
    def update_status(
        self, 
        signal_id: str, 
        status: SignalStatus, 
        notes: Optional[str] = None
    ) -> Optional[Signal]:
        """Update a signal's status."""
        signal = self._signals.get(signal_id)
        if not signal:
            return None
        
        signal.status = status
        signal.updated_at = datetime.now()
        
        if notes:
            signal.content += f"\n\n---\nReview Notes: {notes}"
        
        return signal
    
    def add_enriched(self, enriched: EnrichedSignal) -> None:
        """Add an enriched signal."""
        self._enriched[enriched.id] = enriched
    
    def get_enriched(self, signal_id: str) -> Optional[EnrichedSignal]:
        """Get an enriched signal by ID."""
        return self._enriched.get(signal_id)
    
    def get_all_enriched(self) -> List[EnrichedSignal]:
        """Get all enriched signals."""
        return list(self._enriched.values())
    
    def get_stats(self) -> Stats:
        """Get signal statistics."""
        signals = list(self._signals.values())
        
        if not signals:
            return Stats(
                total=0,
                pending=0,
                approved=0,
                rejected=0,
                by_category={},
                by_source={},
                avg_relevance=0.0
            )
        
        by_category: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        
        for signal in signals:
            cat = signal.category if isinstance(signal.category, str) else signal.category.value
            by_category[cat] = by_category.get(cat, 0) + 1
            by_source[signal.metadata.source] = by_source.get(signal.metadata.source, 0) + 1
        
        return Stats(
            total=len(signals),
            pending=len([s for s in signals if s.status == SignalStatus.PENDING]),
            approved=len([s for s in signals if s.status == SignalStatus.APPROVED]),
            rejected=len([s for s in signals if s.status == SignalStatus.REJECTED]),
            by_category=by_category,
            by_source=by_source,
            avg_relevance=sum(s.relevance_score for s in signals) / len(signals)
        )
    
    def clear(self) -> None:
        """Clear all signals."""
        self._signals.clear()
        self._enriched.clear()


# Global instance
signal_store = SignalStore()


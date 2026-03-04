"""FastAPI backend for Signal Collection."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from typing import List, Optional
from rich.console import Console

from .config import settings
from .models import (
    Signal, EnrichedSignal, Stats,
    ResearchRequest, ResearchResponse,
    UpdateStatusRequest, EnrichmentRequest,
    ExportRequest, ExportResponse, SignalStatus
)
from .services.signal_store import signal_store
from .services.research import research_service
from .services.enrichment import enrichment_service
from .services.export import export_service
from .context_loader import context_loader

console = Console()

# Create FastAPI app
app = FastAPI(
    title="Signal Collection API",
    description="Deep Research & Signal Curation Pipeline for MH-1",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Context Routes ==============

@app.post("/api/context/load")
async def load_context(context_path: str):
    """Load context from a folder path."""
    try:
        context = context_loader.load(context_path)
        return {
            "success": True,
            "founders": len(context.founders),
            "queries": len(context.search_queries)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/context/summary")
async def get_context_summary():
    """Get context summary."""
    return {"summary": context_loader.get_summary()}


# ============== Research Routes ==============

@app.post("/api/research/execute", response_model=ResearchResponse)
async def execute_research(request: ResearchRequest):
    """Execute deep research across all providers."""
    try:
        return await research_service.execute_research(
            context_path=request.context_path,
            custom_queries=request.queries,
            max_signals=request.max_signals
        )
    except Exception as e:
        console.print(f"[red]Research error: {e}[/red]")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/signals", response_model=List[Signal])
async def get_signals(status: Optional[str] = None):
    """Get all signals, optionally filtered by status."""
    if status:
        return signal_store.get_by_status(SignalStatus(status))
    return signal_store.get_all()


@app.get("/api/research/signals/{signal_id}", response_model=Signal)
async def get_signal(signal_id: str):
    """Get a specific signal by ID."""
    signal = signal_store.get(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@app.patch("/api/research/signals/{signal_id}/status", response_model=Signal)
async def update_signal_status(signal_id: str, request: UpdateStatusRequest):
    """Update a signal's status."""
    signal = signal_store.update_status(signal_id, request.status, request.notes)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@app.post("/api/research/signals/batch-update")
async def batch_update_status(updates: List[dict]):
    """Batch update signal statuses."""
    updated = 0
    for update in updates:
        result = signal_store.update_status(
            update["id"], 
            SignalStatus(update["status"])
        )
        if result:
            updated += 1
    return {"updated": updated}


@app.get("/api/research/stats", response_model=Stats)
async def get_stats():
    """Get signal statistics."""
    return signal_store.get_stats()


@app.delete("/api/research/signals")
async def clear_signals():
    """Clear all signals."""
    signal_store.clear()
    return {"success": True}


# ============== Enrichment Routes ==============

@app.post("/api/enrichment/enrich", response_model=List[EnrichedSignal])
async def enrich_signals(request: EnrichmentRequest):
    """Enrich specific signals."""
    return await enrichment_service.enrich_signals(
        request.signal_ids,
        request.depth
    )


@app.post("/api/enrichment/enrich-approved", response_model=List[EnrichedSignal])
async def enrich_all_approved():
    """Enrich all approved signals."""
    return await enrichment_service.enrich_all_approved()


@app.get("/api/enrichment", response_model=List[EnrichedSignal])
async def get_enriched_signals():
    """Get all enriched signals."""
    return signal_store.get_all_enriched()


@app.get("/api/enrichment/{signal_id}", response_model=EnrichedSignal)
async def get_enriched_signal(signal_id: str):
    """Get an enriched signal by ID."""
    enriched = signal_store.get_enriched(signal_id)
    if not enriched:
        raise HTTPException(status_code=404, detail="Enriched signal not found")
    return enriched


# ============== Export Routes ==============

@app.post("/api/export/signals", response_model=ExportResponse)
async def export_signals(request: ExportRequest):
    """Export signals to Google Sheets or Notion."""
    signals = [signal_store.get(sid) for sid in request.signal_ids]
    signals = [s for s in signals if s]
    
    if not signals:
        raise HTTPException(status_code=400, detail="No valid signals found")
    
    if request.destination == "google_sheets":
        return await export_service.export_to_sheets(signals, request.include_enrichment)
    else:
        return await export_service.export_to_notion(signals, request.include_enrichment)


@app.post("/api/export/approved", response_model=ExportResponse)
async def export_approved(
    destination: str = "google_sheets",
    include_enrichment: bool = False
):
    """Export all approved signals."""
    signals = signal_store.get_by_status(SignalStatus.APPROVED)
    
    if not signals:
        return ExportResponse(
            success=False,
            destination=destination,
            exported_count=0,
            error="No approved signals to export"
        )
    
    if destination == "google_sheets":
        return await export_service.export_to_sheets(signals, include_enrichment)
    else:
        return await export_service.export_to_notion(signals, include_enrichment)


@app.post("/api/export/download/csv")
async def download_csv(signal_ids: List[str]):
    """Download signals as CSV."""
    signals = [signal_store.get(sid) for sid in signal_ids]
    signals = [s for s in signals if s]
    
    csv_content = export_service.generate_csv(signals)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=signals.csv"}
    )


@app.post("/api/export/download/json")
async def download_json(signal_ids: List[str]):
    """Download signals as JSON."""
    signals = [signal_store.get(sid) for sid in signal_ids]
    signals = [s for s in signals if s]
    
    json_content = export_service.generate_json(signals)
    return JSONResponse(content=json_content)


# ============== Health Check ==============

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Signal Collection API",
        "version": "1.0.0",
        "docs": "/docs"
    }


def start():
    """Start the server."""
    import uvicorn
    console.print("\n[bold cyan]🚀 Starting Signal Collection API...[/bold cyan]\n")
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )


if __name__ == "__main__":
    start()


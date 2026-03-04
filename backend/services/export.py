"""Export service for Google Sheets and Notion."""

import json
from typing import List, Optional
from datetime import datetime
from rich.console import Console

from ..models import Signal, EnrichedSignal, ExportResponse
from ..config import settings
from .signal_store import signal_store

console = Console()


class ExportService:
    """Service for exporting signals to external platforms."""
    
    async def export_to_sheets(
        self,
        signals: List[Signal],
        include_enrichment: bool = False
    ) -> ExportResponse:
        """Export signals to Google Sheets."""
        if not settings.google_sheets_credentials:
            console.print("[yellow]⚠️ Google Sheets not configured, generating mock export[/yellow]")
            return ExportResponse(
                success=True,
                destination="google_sheets",
                url=f"https://docs.google.com/spreadsheets/d/mock-{int(datetime.now().timestamp())}",
                exported_count=len(signals)
            )
        
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            
            # Parse credentials
            creds_data = json.loads(settings.google_sheets_credentials)
            creds = Credentials.from_service_account_info(
                creds_data,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            client = gspread.authorize(creds)
            
            # Create spreadsheet
            spreadsheet = client.create(
                f"Signal Collection Export - {datetime.now().strftime('%Y-%m-%d')}"
            )
            
            # Signals sheet
            worksheet = spreadsheet.sheet1
            worksheet.update_title("Signals")
            
            headers = [
                "ID", "Title", "Summary", "Category", "Relevance Score",
                "Status", "Source", "Tags", "Created At"
            ]
            
            rows = [[
                s.id, s.title, s.summary, s.category,
                s.relevance_score, s.status, s.metadata.source,
                ", ".join(s.tags), str(s.created_at)
            ] for s in signals]
            
            worksheet.update([headers] + rows)
            
            # If enrichment included, add enrichment sheet
            if include_enrichment:
                enriched = [
                    signal_store.get_enriched(s.id)
                    for s in signals
                ]
                enriched = [e for e in enriched if e]
                
                if enriched:
                    enrich_sheet = spreadsheet.add_worksheet("Enrichment", 100, 20)
                    enrich_headers = [
                        "Signal ID", "Title", "Deep Dive", 
                        "Key Insights", "Recommendations",
                        "Risk Level", "Opportunity Level"
                    ]
                    
                    enrich_rows = [[
                        e.id, e.title, e.enrichment.deep_dive,
                        "\n".join(e.enrichment.key_insights),
                        "\n".join(e.enrichment.actionable_recommendations),
                        e.enrichment.market_impact.risk_level,
                        e.enrichment.market_impact.opportunity_level
                    ] for e in enriched]
                    
                    enrich_sheet.update([enrich_headers] + enrich_rows)
            
            return ExportResponse(
                success=True,
                destination="google_sheets",
                url=spreadsheet.url,
                exported_count=len(signals)
            )
        
        except Exception as e:
            console.print(f"[red]❌ Google Sheets export failed: {e}[/red]")
            return ExportResponse(
                success=False,
                destination="google_sheets",
                exported_count=0,
                error=str(e)
            )
    
    async def export_to_notion(
        self,
        signals: List[Signal],
        include_enrichment: bool = False
    ) -> ExportResponse:
        """Export signals to Notion."""
        if not settings.effective_notion_key:
            console.print("[yellow]⚠️ Notion not configured, generating mock export[/yellow]")
            return ExportResponse(
                success=True,
                destination="notion",
                url=f"https://notion.so/mock-page-{int(datetime.now().timestamp())}",
                exported_count=len(signals)
            )
        
        try:
            from notion_client import Client
            
            notion = Client(auth=settings.effective_notion_key)
            
            # Build page content
            children = [
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": "Signal Collection Report"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": f"Generated: {datetime.now().isoformat()} | Total: {len(signals)} signals"}
                        }]
                    }
                },
                {"object": "block", "type": "divider", "divider": {}},
            ]
            
            # Add signals
            for signal in signals[:20]:  # Limit to avoid API limits
                children.extend([
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": signal.title[:100]}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": f"📊 {signal.relevance_score}% | 🏷️ {signal.category} | {signal.status}"}
                            }]
                        }
                    },
                    {
                        "object": "block",
                        "type": "quote",
                        "quote": {
                            "rich_text": [{"type": "text", "text": {"content": signal.summary[:500]}}]
                        }
                    },
                ])
                
                # Add enrichment if available
                if include_enrichment:
                    enriched = signal_store.get_enriched(signal.id)
                    if enriched:
                        children.extend([
                            {
                                "object": "block",
                                "type": "toggle",
                                "toggle": {
                                    "rich_text": [{"type": "text", "text": {"content": "📖 Enrichment Details"}}],
                                    "children": [
                                        {
                                            "object": "block",
                                            "type": "paragraph",
                                            "paragraph": {
                                                "rich_text": [{"type": "text", "text": {"content": enriched.enrichment.deep_dive[:1000]}}]
                                            }
                                        }
                                    ]
                                }
                            }
                        ])
                
                children.append({"object": "block", "type": "divider", "divider": {}})
            
            # Create page
            parent = {"page_id": settings.notion_database_id} if settings.notion_database_id else {"type": "page_id", "page_id": "root"}
            
            page = notion.pages.create(
                parent=parent,
                properties={
                    "title": {"title": [{"text": {"content": f"Signals - {datetime.now().strftime('%Y-%m-%d')}"}}]}
                },
                children=children
            )
            
            return ExportResponse(
                success=True,
                destination="notion",
                url=f"https://notion.so/{page['id'].replace('-', '')}",
                exported_count=len(signals)
            )
        
        except Exception as e:
            console.print(f"[red]❌ Notion export failed: {e}[/red]")
            return ExportResponse(
                success=False,
                destination="notion",
                exported_count=0,
                error=str(e)
            )
    
    def generate_csv(self, signals: List[Signal]) -> str:
        """Generate CSV content."""
        headers = ["ID", "Title", "Summary", "Category", "Relevance", "Status", "Source", "Tags", "Created"]
        
        rows = [",".join(headers)]
        for s in signals:
            row = [
                s.id,
                f'"{s.title.replace(chr(34), chr(34)+chr(34))}"',
                f'"{s.summary[:200].replace(chr(34), chr(34)+chr(34))}"',
                s.category,
                str(s.relevance_score),
                s.status,
                s.metadata.source,
                f'"{", ".join(s.tags)}"',
                str(s.created_at)
            ]
            rows.append(",".join(row))
        
        return "\n".join(rows)
    
    def generate_json(self, signals: List[Signal]) -> dict:
        """Generate JSON export data."""
        return {
            "export_date": datetime.now().isoformat(),
            "total_signals": len(signals),
            "signals": [s.model_dump() for s in signals]
        }


# Global instance
export_service = ExportService()


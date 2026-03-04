#!/usr/bin/env python3
"""Run Signal Collection application."""

import subprocess
import sys
import os
import time
from pathlib import Path

def main():
    """Main entry point."""
    print("\n" + "="*50)
    print("🚀 Signal Collection Pipeline")
    print("="*50 + "\n")
    
    # Check if we're in the right directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Parse command
    if len(sys.argv) < 2:
        print("Usage: python run.py [backend|frontend|both|test]")
        print("\nCommands:")
        print("  backend   - Start FastAPI backend (port 8000)")
        print("  frontend  - Start Streamlit frontend (port 8501)")
        print("  both      - Start both (requires 2 terminals)")
        print("  test      - Run signal collection test")
        print("  test -s   - Test with social providers (LinkedIn, Reddit, Twitter)")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "backend":
        print("Starting FastAPI backend on http://localhost:8000...")
        print("API docs available at http://localhost:8000/docs\n")
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--reload-exclude", "venv",
            "--reload-exclude", "*.pyc"
        ])
    
    elif command == "frontend":
        print("Starting Streamlit frontend on http://localhost:8501...")
        print("Make sure the backend is running first!\n")
        subprocess.run([
            sys.executable, "-m", "streamlit",
            "run", "frontend/app.py",
            "--server.port", "8501",
            "--server.address", "localhost",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false"
        ])
    
    elif command == "both":
        print("To run both services, open two terminals:")
        print("\nTerminal 1 (Backend):")
        print("  python run.py backend")
        print("\nTerminal 2 (Frontend):")
        print("  python run.py frontend")
        print("\nOr use the provided scripts:")
        print("  ./start_backend.sh")
        print("  ./start_frontend.sh")
    
    elif command == "test":
        import asyncio
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        
        console = Console()
        
        async def run_test():
            from backend.services.research import research_service
            from backend.services.signal_store import signal_store
            from backend.context_loader import context_loader
            
            signal_store.clear()
            context_loader.clear_cache()
            
            console.print(Panel(
                '[bold cyan]🧪 SIGNAL COLLECTION TEST[/bold cyan]\n\n'
                'Running all 7 providers with sample queries',
                border_style='cyan'
            ))
            
            queries = [
                'AI marketing trends 2026',
                'B2B SaaS growth strategies',
                'CMO marketing challenges',
                'marketing automation AI',
                'demand generation B2B',
                'content marketing AI tools',
                'marketing attribution measurement',
                'fractional CMO trends',
            ]
            
            console.print(f'[yellow]Queries:[/yellow]')
            for q in queries:
                console.print(f'  • {q}')
            console.print()
            
            # Check for --social flag
            include_social = '--social' in sys.argv or '-s' in sys.argv
            
            result = await research_service.execute_research(
                './context', 
                custom_queries=queries,
                max_signals=250,
                include_social=include_social
            )
            
            stats = signal_store.get_stats()
            
            # Results table
            table = Table(title='📊 Results', show_header=True, header_style='bold magenta')
            table.add_column('Source', width=12)
            table.add_column('Count', width=8, justify='center')
            
            for src, count in sorted(stats.by_source.items(), key=lambda x: x[1], reverse=True):
                table.add_row(src.capitalize(), f'[green]{count}[/green]' if count > 0 else '0')
            
            table.add_row('[bold]Total[/bold]', f'[bold green]{result.total_found}[/bold green]')
            
            console.print(table)
            console.print(f'[dim]Duration: {result.search_duration_ms/1000:.1f}s[/dim]\n')
            
            # Show signals with URLs
            console.print('[bold]Top Signals:[/bold]\n')
            
            for i, s in enumerate(signal_store.get_all()[:10], 1):
                src = str(s.metadata.source).replace('SignalSource.', '')
                console.print(f'[magenta]{i}. [{src}][/magenta] {s.title[:55]}...')
                if s.metadata.source_url:
                    console.print(f'   [cyan]🔗 {s.metadata.source_url[:70]}[/cyan]')
                console.print()
            
            console.print('[bold green]✅ Test complete![/bold green]')
        
        asyncio.run(run_test())
    
    else:
        print(f"Unknown command: {command}")
        print("Use: backend, frontend, both, or test")
        sys.exit(1)


if __name__ == "__main__":
    main()


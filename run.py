#!/usr/bin/env python3
"""Run Signal Collection application."""

import subprocess
import sys
import os
from pathlib import Path


def main():
    """Main entry point."""
    print("\n" + "=" * 50)
    print("🚀 Signal Collection Pipeline")
    print("=" * 50 + "\n")

    project_root = Path(__file__).parent
    os.chdir(project_root)

    if len(sys.argv) < 2:
        print("Usage: python run.py [server|test]")
        print("\nCommands:")
        print("  server    - Start FastAPI server (port 8000)")
        print("  test      - Run signal collection test")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "server":
        port = os.environ.get("PORT", "8000")
        print(f"Starting Signal Dashboard on http://localhost:{port}...")
        print(f"API docs at http://localhost:{port}/docs\n")
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "server:app",
            "--host", "0.0.0.0",
            "--port", port,
            "--reload",
            "--reload-exclude", "venv",
            "--reload-exclude", "*.pyc"
        ])

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

            console.print('[yellow]Queries:[/yellow]')
            for q in queries:
                console.print(f'  • {q}')
            console.print()

            include_social = '--social' in sys.argv or '-s' in sys.argv

            result = await research_service.execute_research(
                './context',
                custom_queries=queries,
                max_signals=250,
                include_social=include_social
            )

            stats = signal_store.get_stats()

            table = Table(title='📊 Results', show_header=True, header_style='bold magenta')
            table.add_column('Source', width=12)
            table.add_column('Count', width=8, justify='center')

            for src, count in sorted(stats.by_source.items(), key=lambda x: x[1], reverse=True):
                table.add_row(src.capitalize(), f'[green]{count}[/green]' if count > 0 else '0')
            table.add_row('[bold]Total[/bold]', f'[bold green]{result.total_found}[/bold green]')
            console.print(table)
            console.print(f'[dim]Duration: {result.search_duration_ms / 1000:.1f}s[/dim]\n')

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
        print("Use: server or test")
        sys.exit(1)


if __name__ == "__main__":
    main()

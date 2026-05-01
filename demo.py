"""
UBID Fabric — E2E Demo Script
Runs the mock connectors to simulate concurrent data updates,
then fetches the resulting evidence graph to show deterministic convergence.
"""

import asyncio
import httpx
from rich.console import Console
from rich.table import Table

from ubid_fabric.connectors import MockSWSConnector, MockFactoriesConnector

console = Console()

async def run_demo():
    console.print("\n[bold blue]=== UBID Fabric Deterministic Interoperability Demo ===[/bold blue]\n")

    # 1. Start Connectors
    console.print("[yellow]1. Starting Mock Connectors (SWS & Factories)...[/yellow]")
    sws = MockSWSConnector()
    factories = MockFactoriesConnector()

    # Run them concurrently to simulate real-world race conditions
    await asyncio.gather(
        sws.run(),
        factories.run()
    )

    console.print("[green]✔ Connectors emitted events successfully.[/green]\n")
    
    # Wait a tiny bit for processing
    await asyncio.sleep(1)

    # 2. Fetch Events
    ubid = "UBID-KA-2024-00000001"
    console.print(f"[yellow]2. Fetching Canonical Events for {ubid}...[/yellow]")
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:8000/events/{ubid}")
        data = resp.json()
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Event ID (Hash)")
        table.add_column("Source")
        table.add_column("Lamport TS")
        table.add_column("Fields Changed")
        
        for event in data["events"]:
            fields = [fc["field_name"] for fc in event["field_changes"]]
            table.add_row(
                event["event_id"][:12] + "...",
                event["source_system"],
                str(event["lamport_ts"]),
                ", ".join(fields)
            )
        console.print(table)

    # 3. Fetch Evidence Graph
    console.print("\n[yellow]3. Fetching Causal Evidence Graph...[/yellow]")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:8000/evidence/{ubid}")
        data = resp.json()
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Node Type")
        table.add_column("Timestamp")
        table.add_column("Details")
        
        for node in data["nodes"]:
            payload_str = str(node["payload"])
            if len(payload_str) > 60:
                payload_str = payload_str[:57] + "..."
            table.add_row(
                node["node_type"],
                node["timestamp"][:19].replace("T", " "),
                payload_str
            )
        console.print(table)
        
    console.print("\n[bold green]=== Demo Complete ===[/bold green]")

if __name__ == "__main__":
    asyncio.run(run_demo())

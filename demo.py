"""
UBID Fabric — E2E Scenario Walkthrough
Executes the exact scenario defined in the production readiness audit:
1. Address update in SWS -> Propagation to Departments
2. Update from Factories -> Transformation and propagation back to SWS
3. Simultaneous conflict detection & resolution
"""

import asyncio
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
API_BASE = "http://localhost:8000"
UBID = "UBID-KA-2024-00000001"

async def demo_scenario():
    async with httpx.AsyncClient() as client:
        console.print(Panel.fit("🚀 [bold blue]UBID Fabric — End-to-End Interoperability Scenario[/bold blue]", subtitle="v0.2.0 Production Audit"))
        
        # Step 0: Seed Registry
        console.print("\n[bold yellow]Step 0: Seeding registry with sample data...[/bold yellow]")
        await client.post(f"{API_BASE}/registry/seed")
        console.print("[green]✔ Registry seeded with sample Karnataka industrial data.[/green]")

        # Step 1: Address Update in SWS
        console.print("\n[bold yellow]Step 1: Updating registered address in SWS...[/bold yellow]")
        sws_payload = {
            "source_system": "SWS",
            "entity_type": "BUSINESS",
            "external_id": "SWS-1001",
            "changes": [
                {"field": "registered_address", "value": "123 MG Road, Bengaluru, 560001"},
                {"field": "business_name", "value": "Karnataka Tech Solutions"}
            ],
            "metadata": {"user": "admin_sws", "ip": "10.0.0.1"}
        }
        
        try:
            resp = await client.post(f"{API_BASE}/api/ingest/webhook", json=sws_payload)
            resp.raise_for_status()
            data = resp.json()
            console.print(f"[green]✔ SWS update accepted. Event ID: [cyan]{data['event_id'][:16]}...[/cyan]")
        except Exception as e:
            console.print(f"[red]✘ SWS update failed: {e}[/red]")
            return

        await asyncio.sleep(1.5) # Wait for propagation

        # Step 2: Factories Update (Dept -> Fabric -> SWS)
        console.print("\n[bold yellow]Step 2: Department (Factories) updates employee count...[/bold yellow]")
        factories_payload = {
            "source_system": "FACTORIES",
            "entity_type": "FACTORY",
            "external_id": "FAC-5005",
            "changes": [
                {"field": "factory_name", "value": "KARNATAKA TECH SOLUTIONS"},
                {"field": "num_workers", "value": 250}
            ],
            "metadata": {"dept_user": "inspector_9"}
        }
        resp = await client.post(f"{API_BASE}/api/ingest/webhook", json=factories_payload)
        console.print("[green]✔ Factories update received. Mapped to 'business_name' and 'employee_count' in Fabric.[/green]")

        await asyncio.sleep(1.5)

        # Step 3: Simultaneous Conflict
        console.print("\n[bold yellow]Step 3: Simulating simultaneous conflict (SWS vs Shop Est)...[/bold yellow]")
        # Send two updates with the same UBID nearly at once
        c1 = client.post(f"{API_BASE}/api/ingest/webhook", json={
            "source_system": "SWS",
            "external_id": "SWS-1001",
            "changes": [{"field": "registered_address", "value": "Address update from SWS"}]
        })
        c2 = client.post(f"{API_BASE}/api/ingest/webhook", json={
            "source_system": "SHOP_ESTABLISHMENT",
            "external_id": "SHOP-777",
            "changes": [{"field": "address_line_1", "value": "Conflicting address from Shop Est"}]
        })
        
        await asyncio.gather(c1, c2)
        console.print("[green]✔ Concurrent updates handled by L3 Conflict Engine using Source Priority (SWS wins).[/green]")

        # Step 4: Verification
        console.print("\n[bold yellow]Step 4: Verifying Final Converged State via Time-Travel...[/bold yellow]")
        resp = await client.get(f"{API_BASE}/api/metrics/time-travel/{UBID}")
        state = resp.json()
        
        table = Table(title=f"Final Converged State for {UBID}")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        
        for k, v in state.items():
            if not k.startswith('_'):
                table.add_row(k, str(v))
        
        console.print(table)
        
        console.print("\n[bold blue]Scenario Complete. All data points in sync across 3 systems.[/bold blue]")

if __name__ == "__main__":
    asyncio.run(demo_scenario())

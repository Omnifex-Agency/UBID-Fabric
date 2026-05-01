const API_BASE = window.location.origin;

async function fetchStatus() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        const data = await response.json();
        
        // Update indicator
        const dot = document.querySelector('.dot');
        const statusText = document.querySelector('.status-indicator span');
        if(data.status === 'healthy') {
            dot.classList.add('active');
            statusText.textContent = 'System Online';
        } else {
            dot.classList.remove('active');
            statusText.textContent = 'Degraded';
        }

        // Update Stats Grid
        const statsGrid = document.getElementById('statsGrid');
        statsGrid.innerHTML = `
            <div class="stat-card glass-panel">
                <div class="stat-title">Total Canonical Events</div>
                <div class="stat-value">${data.metrics.total_events.toLocaleString()}</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-title">Evidence Nodes</div>
                <div class="stat-value">${data.metrics.evidence_nodes.toLocaleString()}</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-title">Evidence Edges</div>
                <div class="stat-value">${data.metrics.evidence_edges.toLocaleString()}</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-title">Global Lamport Clock</div>
                <div class="stat-value">${data.metrics.lamport_clock}</div>
            </div>
        `;
    } catch (error) {
        console.error("Failed to fetch status:", error);
    }
}

async function fetchEvents() {
    try {
        const response = await fetch(`${API_BASE}/events?limit=10`);
        const data = await response.json();
        
        const tbody = document.getElementById('eventsTableBody');
        tbody.innerHTML = '';
        
        if (data.events.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No events recorded yet.</td></tr>';
            return;
        }

        data.events.forEach(event => {
            const tr = document.createElement('tr');
            
            // Format timestamp
            const date = new Date(event.wall_clock_ts);
            const timeStr = date.toLocaleTimeString() + ' ' + date.toLocaleDateString();
            
            // Format fields
            const fields = event.field_changes.map(fc => fc.field_name).join(', ');

            tr.innerHTML = `
                <td class="hash-cell" title="${event.event_id}">${event.event_id.substring(0, 16)}...</td>
                <td><span class="badge">${event.ubid}</span></td>
                <td><span class="badge">${event.source_system}</span></td>
                <td>T: ${event.lamport_ts}</td>
                <td class="text-muted">${timeStr}</td>
                <td>${fields || 'None'}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error("Failed to fetch events:", error);
    }
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchEvents();
    
    // Auto refresh every 5 seconds
    setInterval(fetchStatus, 5000);
    setInterval(fetchEvents, 5000);
});

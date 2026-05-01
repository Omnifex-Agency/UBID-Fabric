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
    fetchConnectors();
    
    // Auto refresh every 5 seconds
    setInterval(fetchStatus, 5000);
    setInterval(fetchEvents, 5000);

    // Form setup
    const form = document.getElementById('connectorForm');
    if(form) {
        form.addEventListener('submit', handleSaveConnector);
    }

    const tForm = document.getElementById('targetForm');
    if(tForm) {
        tForm.addEventListener('submit', handleSaveTarget);
    }
});

function showTab(tabId) {
    // Hide all tabs
    document.getElementById('dashboardTab').style.display = 'none';
    document.getElementById('hubTab').style.display = 'none';
    document.getElementById('evidenceTab').style.display = 'none';
    document.getElementById('dlqTab').style.display = 'none';
    
    // Show selected tab
    document.getElementById(`${tabId}Tab`).style.display = 'block';
    
    // Update nav links
    document.querySelectorAll('.nav-links a').forEach(a => {
        a.classList.remove('active');
        const linkText = a.textContent.toLowerCase();
        if(linkText.includes(tabId)) a.classList.add('active');
    });

    // Load tab-specific data
    if(tabId === 'evidence') fetchEvidence();
    if(tabId === 'dlq') fetchDLQ();
    if(tabId === 'hub') {
        fetchConnectors();
        fetchTargets();
    }
}

// --- Target Systems Logic ---

function showAddTargetModal() {
    document.getElementById('targetModal').classList.add('active');
}

function hideTargetModal() {
    document.getElementById('targetModal').classList.remove('active');
    document.getElementById('targetForm').reset();
    document.getElementById('targetMappingList').innerHTML = '';
}

function addTargetMappingRow(source = '', target = '') {
    const row = document.createElement('div');
    row.className = 'mapping-row';
    row.innerHTML = `
        <input type="text" class="mapping-source" placeholder="Canonical Field" value="${source}">
        <span class="mapping-sep">→</span>
        <input type="text" class="mapping-target" placeholder="Target Field" value="${target}">
        <button type="button" class="btn-text" style="color: var(--danger)" onclick="this.parentElement.remove()">×</button>
    `;
    document.getElementById('targetMappingList').appendChild(row);
}

async function fetchTargets() {
    try {
        const response = await fetch(`${API_BASE}/api/targets`);
        const targets = await response.json();
        
        const grid = document.getElementById('targetsGrid');
        grid.innerHTML = '';
        
        targets.forEach(target => {
            const config = typeof target.config === 'string' ? JSON.parse(target.config) : target.config;
            const card = document.createElement('div');
            card.className = 'connector-card glass-panel';
            
            card.innerHTML = `
                <div class="connector-header">
                    <div class="connector-info">
                        <h3>${target.name}</h3>
                        <span class="connector-type-badge" style="background: rgba(139, 92, 246, 0.2); color: #a78bfa;">OUTBOUND</span>
                    </div>
                    <div class="dot ${target.is_active ? 'active' : ''}"></div>
                </div>
                <div class="connector-details">
                    <div>System: <strong>${target.system_type}</strong></div>
                    <div class="connector-url">${target.base_url}</div>
                    <div class="connector-metrics">
                        <div class="metric-item">
                            ${Object.keys(config.field_mappings || {}).length} Fields Mapped
                        </div>
                    </div>
                </div>
                <div class="connector-actions">
                    <button class="btn" style="background: rgba(255,255,255,0.05); color: #fff;" onclick="toggleTarget('${target.id}')">
                        ${target.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button class="btn" style="background: rgba(239, 68, 68, 0.1); color: var(--danger);" onclick="deleteTarget('${target.id}')">Delete</button>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (error) {
        console.error("Failed to fetch targets:", error);
    }
}

async function handleSaveTarget(e) {
    e.preventDefault();
    
    const mappings = {};
    document.querySelectorAll('#targetMappingList .mapping-row').forEach(row => {
        const source = row.querySelector('.mapping-source').value;
        const target = row.querySelector('.mapping-target').value;
        if(source && target) mappings[source] = target;
    });

    const payload = {
        name: document.getElementById('targetName').value,
        system_type: document.getElementById('targetSystem').value,
        base_url: document.getElementById('targetUrl').value,
        auth_header: document.getElementById('targetAuth').value,
        config: {
            method: document.getElementById('targetMethod').value,
            field_mappings: mappings
        },
        is_active: true
    };

    try {
        const response = await fetch(`${API_BASE}/api/targets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if(response.ok) {
            hideTargetModal();
            fetchTargets();
        }
    } catch (error) {
        console.error("Failed to save target:", error);
    }
}

async function toggleTarget(id) {
    await fetch(`${API_BASE}/api/targets/${id}/toggle`, { method: 'PATCH' });
    fetchTargets();
}

async function deleteTarget(id) {
    if(confirm('Are you sure you want to delete this target system?')) {
        await fetch(`${API_BASE}/api/targets/${id}`, { method: 'DELETE' });
        fetchTargets();
    }
}

async function fetchEvidence() {
    try {
        const response = await fetch(`${API_BASE}/api/evidence`);
        const nodes = await response.json();
        
        const tbody = document.getElementById('evidenceTableBody');
        tbody.innerHTML = '';
        
        if (nodes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No evidence nodes recorded yet.</td></tr>';
            return;
        }

        nodes.forEach(node => {
            const tr = document.createElement('tr');
            const date = new Date(node.timestamp);
            const timeStr = date.toLocaleTimeString() + ' ' + date.toLocaleDateString();
            
            tr.innerHTML = `
                <td><span class="badge" style="background: rgba(59, 130, 246, 0.1); color: var(--accent);">${node.node_type}</span></td>
                <td><span class="badge">${node.ubid || 'N/A'}</span></td>
                <td class="hash-cell">${node.event_id ? node.event_id.substring(0, 12) + '...' : 'System'}</td>
                <td class="text-muted">${timeStr}</td>
                <td><small>${JSON.stringify(node.payload).substring(0, 50)}...</small></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error("Failed to fetch evidence:", error);
    }
}

async function fetchDLQ() {
    try {
        const response = await fetch(`${API_BASE}/api/dlq`);
        const entries = await response.json();
        
        const tbody = document.getElementById('dlqTableBody');
        tbody.innerHTML = '';
        
        if (entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Dead Letter Queue is empty. Everything synced!</td></tr>';
            return;
        }

        entries.forEach(entry => {
            const tr = document.createElement('tr');
            const date = new Date(entry.created_at);
            
            tr.innerHTML = `
                <td class="hash-cell">${entry.event_id.substring(0, 12)}...</td>
                <td><span class="badge">${entry.ubid}</span></td>
                <td><strong>${entry.target_system}</strong></td>
                <td><span class="badge" style="background: rgba(239, 68, 68, 0.1); color: var(--danger);">${entry.status}</span></td>
                <td class="text-muted">${date.toLocaleString()}</td>
                <td>
                    <button class="btn btn-primary" style="padding: 0.3rem 0.7rem; font-size: 0.8rem;" onclick="retryDLQ(${entry.dlq_id})">Retry</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error("Failed to fetch DLQ:", error);
    }
}

async function retryDLQ(id) {
    try {
        const response = await fetch(`${API_BASE}/api/dlq/${id}/retry`, { method: 'POST' });
        if(response.ok) {
            alert('Retry initiated for event propagation.');
            fetchDLQ();
        }
    } catch (error) {
        console.error("Failed to retry DLQ entry:", error);
    }
}

function showAddConnectorModal() {
    document.getElementById('connectorModal').classList.add('active');
}

function hideConnectorModal() {
    document.getElementById('connectorModal').classList.remove('active');
    document.getElementById('connectorForm').reset();
}

async function fetchConnectors() {
    try {
        const response = await fetch(`${API_BASE}/api/connectors`);
        const connectors = await response.json();
        
        const grid = document.getElementById('connectorsGrid');
        grid.innerHTML = '';
        
        connectors.forEach(conn => {
            const config = typeof conn.config === 'string' ? JSON.parse(conn.config) : conn.config;
            const card = document.createElement('div');
            card.className = 'connector-card glass-panel';
            
            const statusClass = conn.last_status === 'SUCCESS' ? 'metric-success' : (conn.last_status === 'FAILED' ? 'metric-failed' : '');
            
            card.innerHTML = `
                <div class="connector-header">
                    <div class="connector-info">
                        <h3>${conn.name}</h3>
                        <span class="connector-type-badge">${conn.connector_type}</span>
                    </div>
                    <div class="dot ${conn.is_active ? 'active' : ''}"></div>
                </div>
                <div class="connector-details">
                    <div>System: <strong>${conn.system_type}</strong></div>
                    <div class="connector-url">${config.url || 'Internal / Direct'}</div>
                    <div class="connector-metrics">
                        <div class="metric-item ${statusClass}">
                            ● ${conn.last_status}
                        </div>
                        <div class="metric-item">
                            SR: ${conn.success_rate}%
                        </div>
                    </div>
                </div>
                <div class="connector-actions">
                    <button class="btn" style="background: rgba(255,255,255,0.05); color: #fff;" onclick="toggleConnector('${conn.id}')">
                        ${conn.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button class="btn" style="background: rgba(239, 68, 68, 0.1); color: var(--danger);" onclick="deleteConnector('${conn.id}')">Delete</button>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (error) {
        console.error("Failed to fetch connectors:", error);
    }
}

async function handleSaveConnector(e) {
    e.preventDefault();
    
    // Collect mappings
    const mappings = {};
    document.querySelectorAll('.mapping-row').forEach(row => {
        const source = row.querySelector('.mapping-source').value;
        const canonical = row.querySelector('.mapping-target').value;
        if(source && canonical) mappings[source] = canonical;
    });

    const payload = {
        name: document.getElementById('connName').value,
        system_type: document.getElementById('connSystem').value,
        connector_type: document.getElementById('connType').value,
        config: {
            url: document.getElementById('connUrl').value,
            interval_seconds: parseInt(document.getElementById('connInterval').value),
            auth_header: document.getElementById('connAuth').value,
            field_mappings: mappings
        },
        is_active: true
    };

    try {
        const response = await fetch(`${API_BASE}/api/connectors`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if(response.ok) {
            hideConnectorModal();
            fetchConnectors();
        }
    } catch (error) {
        console.error("Failed to save connector:", error);
    }
}

async function testConnector() {
    const config = {
        url: document.getElementById('connUrl').value,
        method: "GET",
        auth_header: document.getElementById('connAuth').value
    };
    
    const btn = document.querySelector('button[onclick="testConnector()"]');
    btn.textContent = "Testing...";
    
    try {
        const response = await fetch(`${API_BASE}/api/connectors/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await response.json();
        
        if(data.status === 'success') {
            document.getElementById('testResultArea').style.display = 'block';
            document.getElementById('sampleJson').textContent = JSON.stringify(data.sample_data, null, 2);
            window.currentSample = data.sample_data;
        } else {
            alert("Test Failed: " + data.message);
        }
    } catch (error) {
        alert("Connection Error");
    } finally {
        btn.textContent = "Test";
    }
}

async function autoMapFields() {
    if(!window.currentSample) return;
    
    const btn = document.querySelector('button[onclick="autoMapFields()"]');
    btn.textContent = "AI Mapping...";
    
    try {
        const response = await fetch(`${API_BASE}/api/connectors/auto-map`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_sample: window.currentSample })
        });
        const data = await response.json();
        const mapping = data.suggestion;
        
        // Clear existing and add AI suggested rows
        document.getElementById('mappingList').innerHTML = '';
        Object.entries(mapping).forEach(([source, target]) => {
            addMappingRow(source, target);
        });
    } catch (error) {
        alert("AI Mapping Failed");
    } finally {
        btn.textContent = "Auto-Map with AI";
    }
}

function addMappingRow(source = '', target = '') {
    const row = document.createElement('div');
    row.className = 'mapping-row';
    row.innerHTML = `
        <input type="text" class="mapping-source" placeholder="Source Field" value="${source}">
        <span class="mapping-sep">→</span>
        <input type="text" class="mapping-target" placeholder="Canonical Field" value="${target}">
        <button type="button" class="btn-text" style="color: var(--danger)" onclick="this.parentElement.remove()">×</button>
    `;
    document.getElementById('mappingList').appendChild(row);
}

async function toggleConnector(id) {
    await fetch(`${API_BASE}/api/connectors/${id}/toggle`, { method: 'PATCH' });
    fetchConnectors();
}

async function deleteConnector(id) {
    if(confirm('Are you sure you want to delete this connector?')) {
        await fetch(`${API_BASE}/api/connectors/${id}`, { method: 'DELETE' });
        fetchConnectors();
    }
}

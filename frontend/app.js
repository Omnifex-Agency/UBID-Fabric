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
                <td><span class="badge" style="background: var(--zebra-striping); color: var(--primary); border: 1px solid var(--border-light); font-family: 'JetBrains Mono', monospace;">${event.ubid}</span></td>
                <td><span class="badge" style="background: rgba(45, 106, 79, 0.1); color: var(--accent); border: 1px solid rgba(45, 106, 79, 0.2);">${event.source_system}</span></td>
                <td><small style="font-family: 'JetBrains Mono', monospace; font-weight: 600;">T: ${event.lamport_ts}</small></td>
                <td class="text-muted">${timeStr}</td>
                <td style="font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--accent);">${fields || 'None'}</td>
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

    const sandboxForm = document.getElementById('sandboxForm');
    if(sandboxForm) {
        sandboxForm.addEventListener('submit', handleSandboxSubmit);
    }
});

function showTab(tabId) {
    // Hide all tabs
    document.querySelectorAll('main > div').forEach(div => div.style.display = 'none');
    
    // Show selected tab
    const target = document.getElementById(`${tabId}Tab`);
    if(target) target.style.display = 'block';
    
    // Update nav links
    document.querySelectorAll('.nav-links a').forEach(a => {
        a.classList.remove('active');
        const onclickStr = a.getAttribute('onclick') || '';
        if(onclickStr.includes(`'${tabId}'`)) a.classList.add('active');
    });

    // Load tab-specific data
    if(tabId === 'evidence') fetchEvidence();
    if(tabId === 'dlq') fetchDLQ();
    if(tabId === 'hub') {
        fetchConnectors();
        fetchTargets();
    }
    if(tabId === 'metrics') {
        fetchMetrics();
        fetchDriftAnalytics();
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
            
            let badgeStyle = "background: rgba(13, 40, 24, 0.05); color: var(--primary); border: 1px solid rgba(13, 40, 24, 0.1);";
            if(node.node_type.includes('CONFLICT')) badgeStyle = "background: rgba(244, 162, 97, 0.1); color: var(--warning); border: 1px solid rgba(244, 162, 97, 0.2);";
            if(node.node_type.includes('DLQ') || node.node_type.includes('FAILED')) badgeStyle = "background: rgba(188, 71, 73, 0.1); color: var(--danger); border: 1px solid rgba(188, 71, 73, 0.2);";
            if(node.node_type.includes('SUCCESS') || node.node_type.includes('CONFIRMATION')) badgeStyle = "background: rgba(116, 198, 157, 0.1); color: var(--success); border: 1px solid rgba(116, 198, 157, 0.2);";

            tr.innerHTML = `
                <td><span class="badge" style="${badgeStyle}">${node.node_type}</span></td>
                <td><span class="badge" style="background: var(--zebra-striping); color: var(--text-main); border: 1px solid var(--border-light); font-family: 'JetBrains Mono', monospace;">${node.ubid || 'N/A'}</span></td>
                <td class="hash-cell">${node.event_id ? node.event_id.substring(0, 12) + '...' : 'System'}</td>
                <td class="text-muted">${timeStr}</td>
                <td><small style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--accent);">${JSON.stringify(node.payload).substring(0, 120)}...</small></td>
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
                <td><span class="badge" style="background: var(--zebra-striping); color: var(--primary); border: 1px solid var(--border-light); font-family: 'JetBrains Mono', monospace;">${entry.ubid}</span></td>
                <td><strong>${entry.target_system}</strong></td>
                <td><span class="badge" style="background: rgba(188, 71, 73, 0.1); color: var(--danger); border: 1px solid rgba(188, 71, 73, 0.2); font-weight: 600;">${entry.status}</span></td>
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

async function runDryRun() {
    if(!window.currentSample) {
        alert("Please test the connector first to get sample data.");
        return;
    }

    // Collect current mappings from the UI
    const mappings = {};
    document.querySelectorAll('#mappingList .mapping-row').forEach(row => {
        const source = row.querySelector('.mapping-source').value;
        const target = row.querySelector('.mapping-target').value;
        if(source && target) mappings[source] = target;
    });

    const payload = {
        source_data: window.currentSample,
        field_mappings: mappings
    };

    try {
        const response = await fetch(`${API_BASE}/api/simulator/dry-run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        
        if(data.status === 'success') {
            document.getElementById('simulatorOutputArea').style.display = 'block';
            document.getElementById('simulatorJson').textContent = JSON.stringify(data.transformed_data, null, 2);
            document.getElementById('simMappingCount').textContent = `${data.mapping_count} fields matched`;
        }
    } catch (error) {
        alert("Simulator Error");
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

// ═══════════════════════════════════════════════════════════════
// Phase 5: Metrics & Observability
// ═══════════════════════════════════════════════════════════════

async function fetchMetrics() {
    try {
        const response = await fetch(`${API_BASE}/api/metrics`);
        const data = await response.json();

        const grid = document.getElementById('metricsGrid');
        grid.innerHTML = `
            <div class="stat-card glass-panel">
                <div class="stat-title">Events (Last Hour)</div>
                <div class="stat-value">${data.events_last_hour}</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-title">DLQ Depth</div>
                <div class="stat-value" style="color: ${data.dlq_depth > 0 ? 'var(--danger)' : 'var(--success)'}">${data.dlq_depth}</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-title">Conflicts (24h)</div>
                <div class="stat-value">${data.conflicts_24h}</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-title">Propagation Success</div>
                <div class="stat-value" style="color: ${data.propagation_success_rate >= 95 ? 'var(--success)' : 'var(--danger)'}">${data.propagation_success_rate}%</div>
            </div>
        `;

        // Source breakdown chart (simple bar visualization)
        const chart = document.getElementById('sourceBreakdownChart');
        if (data.source_breakdown.length === 0) {
            chart.innerHTML = '<p class="text-muted">No events recorded yet.</p>';
            return;
        }
        const maxEvents = Math.max(...data.source_breakdown.map(s => s.events));
        chart.innerHTML = data.source_breakdown.map(s => `
            <div style="display: flex; align-items: center; margin-bottom: 0.8rem; gap: 1rem;">
                <span style="min-width: 140px; font-weight: 600; color: #fff;">${s.system}</span>
                <div style="flex: 1; background: rgba(255,255,255,0.05); border-radius: 4px; overflow: hidden;">
                    <div style="width: ${(s.events / maxEvents) * 100}%; background: linear-gradient(90deg, var(--accent), #8b5cf6); padding: 0.4rem 0.8rem; color: #fff; font-size: 0.85rem; border-radius: 4px;">
                        ${s.events} events
                    </div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error("Failed to fetch metrics:", error);
    }
}

async function fetchDriftAnalytics() {
    try {
        const response = await fetch(`${API_BASE}/api/metrics/drift`);
        const data = await response.json();

        const tbody = document.getElementById('driftTableBody');
        tbody.innerHTML = '';

        if (data.dlq_failures_by_system.length === 0) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-muted">No drift detected. All systems in sync!</td></tr>';
            return;
        }

        data.dlq_failures_by_system.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${item.system}</strong></td>
                <td><span class="badge" style="background: rgba(239, 68, 68, 0.1); color: var(--danger);">${item.failures} failures</span></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error("Failed to fetch drift analytics:", error);
    }
}

async function runTimeTravel() {
    const ubid = document.getElementById('ttUbid').value;
    const asOf = document.getElementById('ttAsOf').value;

    if (!ubid) {
        alert('Please enter a UBID.');
        return;
    }

    let url = `${API_BASE}/api/metrics/time-travel/${ubid}`;
    if (asOf) url += `?as_of=${encodeURIComponent(asOf)}`;

    try {
        const response = await fetch(url);
        const data = await response.json();

        const output = document.getElementById('timeTravelOutput');
        output.style.display = 'block';
        output.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        alert('Time-Travel failed: ' + error.message);
    }
}

async function runSnapshotCompare() {
    const ubid = document.getElementById('snapUbid').value;
    const timeA = document.getElementById('snapTimeA').value;
    const timeB = document.getElementById('snapTimeB').value;

    if (!ubid) {
        alert('Please enter a UBID.');
        return;
    }

    const btn = document.querySelector('button[onclick="runSnapshotCompare()"]');
    btn.textContent = "Comparing...";
    btn.disabled = true;

    let urlA = `${API_BASE}/api/metrics/time-travel/${ubid}`;
    if (timeA) urlA += `?as_of=${encodeURIComponent(timeA)}`;
    
    let urlB = `${API_BASE}/api/metrics/time-travel/${ubid}`;
    if (timeB) urlB += `?as_of=${encodeURIComponent(timeB)}`;

    try {
        const [resA, resB] = await Promise.all([
            fetch(urlA),
            fetch(urlB)
        ]);

        const dataA = await resA.json();
        const dataB = await resB.json();

        document.getElementById('snapshotOutput').style.display = 'block';
        document.getElementById('snapAOutput').textContent = JSON.stringify(dataA, null, 2);
        document.getElementById('snapBOutput').textContent = JSON.stringify(dataB, null, 2);
    } catch (error) {
        alert('Snapshot Comparison failed: ' + error.message);
    } finally {
        btn.textContent = "Compare Snapshots";
        btn.disabled = false;
    }
}

// ═══════════════════════════════════════════════════════════════
// Phase 3: CSV File Upload
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('fileUploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleFileUpload);
    }
});

async function handleFileUpload(e) {
    e.preventDefault();

    const fileInput = document.getElementById('csvFile');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('source_system', document.getElementById('fileSource').value);
    formData.append('entity_type', document.getElementById('fileEntityType').value);
    formData.append('field_mappings', document.getElementById('fileMappings').value);

    try {
        const response = await fetch(`${API_BASE}/api/ingest/file`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        document.getElementById('fileUploadResult').style.display = 'block';
        document.getElementById('fileResultJson').textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

// ═══════════════════════════════════════════════════════════════
// Phase 6: API Sandbox (Postman-like Tester)
// ═══════════════════════════════════════════════════════════════

async function handleSandboxSubmit(e) {
    e.preventDefault();
    
    const btn = document.querySelector('#sandboxForm button[type="submit"]');
    btn.textContent = "Sending...";
    btn.disabled = true;

    const source = document.getElementById('sbSource').value;
    const entityId = document.getElementById('sbEntityId').value;
    const name = document.getElementById('sbName').value;
    
    let changes = [];
    try {
        changes = JSON.parse(document.getElementById('sbChanges').value);
    } catch(err) {
        alert("Invalid JSON in Changes array!");
        btn.textContent = "Send Request";
        btn.disabled = false;
        return;
    }

    const payload = {
        source_system: source,
        entity_type: "FACTORY",
        entity_id: entityId,
        business_name: name,
        address: "",
        changes: changes,
        timestamp: new Date().toISOString()
    };

    try {
        const response = await fetch(`${API_BASE}/api/ingest/webhook`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        // Update Response Pane
        document.getElementById('sbResponseArea').style.display = 'block';
        document.getElementById('sbResponseJson').textContent = JSON.stringify(data, null, 2);
        
        const badge = document.getElementById('sbStatusBadge');
        const codeText = document.getElementById('sbStatusCode');
        const dot = badge.querySelector('.dot');
        
        codeText.textContent = `${response.status} ${response.ok ? 'OK' : 'Error'}`;
        
        if (response.ok) {
            dot.style.background = 'var(--success)';
            dot.style.boxShadow = '0 0 0 3px var(--success-bg)';
        } else {
            dot.style.background = 'var(--danger)';
            dot.style.boxShadow = '0 0 0 3px var(--danger-bg)';
        }

        // Auto-refresh tables to show new data
        fetchEvents();
        fetchEvidence();
        fetchMetrics();
        
    } catch (error) {
        document.getElementById('sbResponseArea').style.display = 'block';
        document.getElementById('sbResponseJson').textContent = error.message;
        
        const badge = document.getElementById('sbStatusBadge');
        document.getElementById('sbStatusCode').textContent = "Connection Error";
        const dot = badge.querySelector('.dot');
        dot.style.background = 'var(--danger)';
        dot.style.boxShadow = '0 0 0 3px var(--danger-bg)';
    } finally {
        btn.textContent = "Send Request";
        btn.disabled = false;
    }
}

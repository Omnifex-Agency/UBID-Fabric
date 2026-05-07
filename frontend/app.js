const API_BASE = window.location.origin;

// ═══════════════════════════════════════════════════════════════
// Phase 1: Core Lifecycle & Global Status
// ═══════════════════════════════════════════════════════════════

async function fetchStatus() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        const data = await response.json();
        
        const dot = document.querySelector('.dot');
        const statusText = document.querySelector('.status-indicator span');
        if(data.status === 'healthy') {
            dot.classList.add('active');
            statusText.textContent = 'System Online';
        } else {
            dot.classList.remove('active');
            statusText.textContent = 'Degraded';
        }

        const statsGrid = document.getElementById('statsGrid');
        if (statsGrid) {
            statsGrid.innerHTML = `
                <div class="stat-card glass-panel">
                    <div class="stat-title">Canonical Events</div>
                    <div class="stat-value">${data.metrics.total_events.toLocaleString()}</div>
                </div>
                <div class="stat-card glass-panel">
                    <div class="stat-title">Evidence Nodes</div>
                    <div class="stat-value">${data.metrics.evidence_nodes.toLocaleString()}</div>
                </div>
                <div class="stat-card glass-panel">
                    <div class="stat-title">Propagation Success</div>
                    <div class="stat-value">${data.metrics.propagation_success_rate}%</div>
                </div>
                <div class="stat-card glass-panel">
                    <div class="stat-title">Lamport Clock</div>
                    <div class="stat-value">${data.metrics.lamport_clock}</div>
                </div>
            `;
        }
    } catch (error) {
        console.error("Status check failed", error);
    }
}

async function fetchEvents() {
    try {
        const response = await fetch(`${API_BASE}/events?limit=10`);
        const data = await response.json();
        const tbody = document.getElementById('eventsTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        
        if (data.events.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No events recorded.</td></tr>';
            return;
        }

        data.events.forEach(event => {
            const tr = document.createElement('tr');
            const date = new Date(event.wall_clock_ts);
            const fields = event.field_changes.map(fc => fc.field_name).join(', ');
            tr.innerHTML = `
                <td class="hash-cell" title="${event.event_id}">${event.event_id.substring(0, 12)}...</td>
                <td><span class="badge">${event.ubid}</span></td>
                <td><span class="badge" style="background: rgba(45, 106, 79, 0.1); color: var(--accent);">${event.source_system}</span></td>
                <td>T: ${event.lamport_ts}</td>
                <td class="text-muted">${date.toLocaleTimeString()}</td>
                <td style="font-family: monospace; font-size: 0.8rem; color: var(--accent);">${fields}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) { console.error(error); }
}

// ═══════════════════════════════════════════════════════════════
// Phase 2: Navigation & Tab Logic
// ═══════════════════════════════════════════════════════════════

function showTab(tabId) {
    // Hide all tabs
    document.querySelectorAll('main > .tab-panel').forEach(div => div.style.display = 'none');
    
    // Show selected tab
    const target = document.getElementById(tabId);
    if(target) target.style.display = 'block';
    
    // Update nav links
    document.querySelectorAll('.nav-links button').forEach(button => {
        button.classList.remove('active');
        const onclickStr = button.getAttribute('onclick') || '';
        if(onclickStr.includes(`'${tabId}'`)) button.classList.add('active');
    });

    // Refresh tab data
    if(tabId === 'dashboardTab') { fetchEvents(); fetchStatus(); }
    if(tabId === 'hubTab') { fetchNodes(); fetchDLQ(); }
    if(tabId === 'auditTab') { fetchEvidence(); fetchMetrics(); fetchDriftAnalytics(); }
    if(tabId === 'simulatedTab') { fetchSimulatedState(); }
}

// ═══════════════════════════════════════════════════════════════
// Phase 3: Hub, Routing & DLQ
// ═══════════════════════════════════════════════════════════════

async function fetchNodes() {
    try {
        const response = await fetch(`${API_BASE}/api/nodes`);
        const nodes = await response.json();
        const grid = document.getElementById('nodesGrid');
        if(!grid) return;
        
        grid.innerHTML = nodes.map(node => `
            <div class="node-card glass-panel">
                <div class="node-header">
                    <div class="dept-icon ${node.system_type.toLowerCase()}" style="width: 24px; height: 24px; border-radius: 4px;"></div>
                    <h3>${node.system_type}</h3>
                </div>
                <div class="node-channels">
                    <div class="channel ${node.ingress?.is_active ? 'active' : ''}">
                        <div class="channel-info">
                            <span class="channel-label">Ingress (In)</span>
                            <span class="channel-status">${node.ingress ? node.ingress.type : 'Not Setup'}</span>
                        </div>
                        <div class="dot ${node.ingress?.is_active ? 'active' : ''}"></div>
                    </div>
                    <div class="channel ${node.egress?.is_active ? 'active' : ''}">
                        <div class="channel-info">
                            <span class="channel-label">Egress (Out)</span>
                            <span class="channel-status">${node.egress ? 'Connected' : 'Not Setup'}</span>
                        </div>
                        <div class="dot ${node.egress?.is_active ? 'active' : ''}"></div>
                    </div>
                </div>
                <div class="node-footer">
                    <span class="text-muted" style="font-size: 0.7rem;">SR: ${node.ingress?.success_rate || 100}%</span>
                </div>
            </div>
        `).join('');
    } catch(e) { console.error(e); }
}

async function fetchDLQ() {
    try {
        const response = await fetch(`${API_BASE}/api/dlq`);
        const entries = await response.json();
        const tbody = document.getElementById('dlqTableBody');
        if(!tbody) return;
        tbody.innerHTML = entries.length === 0 ? '<tr><td colspan="6" class="text-center text-muted">DLQ is empty.</td></tr>' : 
            entries.map(e => `
                <tr>
                    <td class="hash-cell">${e.event_id.substring(0, 12)}...</td>
                    <td>${e.ubid}</td>
                    <td><strong>${e.target_system}</strong></td>
                    <td><span class="badge" style="background: rgba(188,71,73,0.1); color: var(--danger);">${e.status}</span></td>
                    <td class="text-muted">${new Date(e.created_at).toLocaleString()}</td>
                    <td><button class="btn btn-primary btn-sm" onclick="retryDLQ(${e.dlq_id})">Retry</button></td>
                </tr>
            `).join('');
    } catch(e) { console.error(e); }
}

async function retryDLQ(id) {
    await fetch(`${API_BASE}/api/dlq/${id}/retry`, { method: 'POST' });
    fetchDLQ();
}

// ═══════════════════════════════════════════════════════════════
// Phase 4: Audit, Metrics & Time-Travel
// ═══════════════════════════════════════════════════════════════

async function fetchEvidence() {
    try {
        const response = await fetch(`${API_BASE}/api/evidence`);
        const nodes = await response.json();
        const tbody = document.getElementById('evidenceTableBody');
        if(!tbody) return;
        tbody.innerHTML = nodes.map(n => `
            <tr>
                <td><span class="badge">${n.node_type}</span></td>
                <td>${n.ubid || 'System'}</td>
                <td class="hash-cell">${n.event_id ? n.event_id.substring(0, 12) : '---'}</td>
                <td class="text-muted">${new Date(n.timestamp).toLocaleTimeString()}</td>
                <td><small style="font-family: monospace; font-size: 0.7rem; color: var(--accent);">${JSON.stringify(n.payload).substring(0, 80)}...</small></td>
            </tr>
        `).join('');
    } catch(e) { console.error(e); }
}

async function fetchMetrics() {
    try {
        const response = await fetch(`${API_BASE}/api/metrics`);
        const data = await response.json();
        const grid = document.getElementById('metricsGrid');
        if(!grid) return;
        grid.innerHTML = `
            <div class="stat-card glass-panel"><h3>Events (1h)</h3><div class="stat-value">${data.events_last_hour}</div></div>
            <div class="stat-card glass-panel"><h3>DLQ Depth</h3><div class="stat-value">${data.dlq_depth}</div></div>
            <div class="stat-card glass-panel"><h3>Conflicts</h3><div class="stat-value">${data.conflicts_24h}</div></div>
            <div class="stat-card glass-panel"><h3>Active UBIDs</h3><div class="stat-value">${data.active_ubids_24h}</div></div>
        `;
        
        const chart = document.getElementById('sourceBreakdownChart');
        if(chart) {
            chart.innerHTML = data.source_breakdown.map(s => `
                <div style="margin-bottom: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 2px;">
                        <span>${s.system}</span><span>${s.events}</span>
                    </div>
                    <div style="height: 6px; background: rgba(255,255,255,0.05); border-radius: 3px;">
                        <div style="height: 100%; width: ${data.total_events ? (s.events / data.total_events) * 100 : 0}%; background: var(--accent); border-radius: 3px;"></div>
                    </div>
                </div>
            `).join('');
        }
    } catch(e) { console.error(e); }
}

async function fetchDriftAnalytics() {
    try {
        const response = await fetch(`${API_BASE}/api/metrics/drift`);
        const data = await response.json();
        const tbody = document.getElementById('driftTableBody');
        if(!tbody) return;
        tbody.innerHTML = data.dlq_failures_by_system.map(item => `
            <tr><td>${item.system}</td><td>${item.failures} failures</td></tr>
        `).join('') || '<tr><td colspan="2" class="text-center text-muted">All systems in sync.</td></tr>';
    } catch(e) { console.error(e); }
}

async function runTimeTravel() {
    const ubid = document.getElementById('ttUbid').value;
    const asOf = document.getElementById('ttAsOf').value;
    if(!ubid) return alert("Enter UBID");
    
    let url = `${API_BASE}/api/metrics/time-travel/${ubid}`;
    if(asOf) url += `?as_of=${encodeURIComponent(asOf)}`;
    
    const res = await fetch(url);
    const data = await res.json();
    const output = document.getElementById('timeTravelOutput');
    output.style.display = 'block';
    output.textContent = JSON.stringify(data, null, 2);
}

async function runSnapshotCompare() {
    const ubid = document.getElementById('ttUbid').value;
    const timeA = document.getElementById('ttAsOf').value;
    const timeB = document.getElementById('snapTimeB').value;
    if(!ubid) return alert("Enter UBID");

    document.getElementById('snapshotOutput').style.display = 'grid';
    
    const [resA, resB] = await Promise.all([
        fetch(`${API_BASE}/api/metrics/time-travel/${ubid}${timeA ? '?as_of='+encodeURIComponent(timeA) : ''}`),
        fetch(`${API_BASE}/api/metrics/time-travel/${ubid}${timeB ? '?as_of='+encodeURIComponent(timeB) : ''}`)
    ]);
    
    document.getElementById('snapAOutput').textContent = JSON.stringify(await resA.json(), null, 2);
    document.getElementById('snapBOutput').textContent = JSON.stringify(await resB.json(), null, 2);
}

// ═══════════════════════════════════════════════════════════════
// Phase 5: Ingestion Tools & Sandbox
// ═══════════════════════════════════════════════════════════════

async function handleSandboxSubmit(e) {
    e.preventDefault();
    const payload = {
        source_system: document.getElementById('sbSource').value,
        ubid: document.getElementById('sbUbid').value || null,
        entity_type: "FACTORY",
        entity_id: document.getElementById('sbEntityId').value,
        changes: JSON.parse(document.getElementById('sbChanges').value),
        timestamp: new Date().toISOString()
    };

    const res = await fetch(`${API_BASE}/api/ingest/webhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    
    const data = await res.json();
    document.getElementById('sbResponseArea').style.display = 'block';
    document.getElementById('sbStatusCode').textContent = `${res.status} ${res.statusText}`;
    document.getElementById('sbResponseJson').textContent = JSON.stringify(data, null, 2);
}

async function handleFileUpload(e) {
    e.preventDefault();
    const formData = new FormData();
    formData.append('file', document.getElementById('csvFile').files[0]);
    formData.append('source_system', document.getElementById('fileSource').value);
    formData.append('entity_type', document.getElementById('fileEntityType').value);

    const res = await fetch(`${API_BASE}/api/ingest/file`, { method: 'POST', body: formData });
    document.getElementById('fileUploadResult').style.display = 'block';
    document.getElementById('fileResultJson').textContent = JSON.stringify(await res.json(), null, 2);
}

async function handleConnectorSubmit(e) {
    e.preventDefault();
    const payload = {
        name: document.getElementById('connName').value,
        system_type: document.getElementById('connSystem').value.toUpperCase(),
        connector_type: document.getElementById('connType').value,
        config: {
            url: document.getElementById('connUrl').value || null,
            method: document.getElementById('connType').value === 'WEBHOOK' ? 'POST' : 'GET',
            field_mappings: {}
        }
    };

    const res = await fetch(`${API_BASE}/api/connectors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    if (!res.ok) {
        alert('Connector setup failed');
        return;
    }

    hideConnectorModal();
    e.target.reset();
    fetchNodes();
}

async function handleTargetSubmit(e) {
    e.preventDefault();
    const payload = {
        name: document.getElementById('tName').value,
        system_type: document.getElementById('tSystem').value.toUpperCase(),
        base_url: document.getElementById('tUrl').value,
        config: {
            method: document.getElementById('tMethod').value,
            field_mappings: {},
            payload_template: {}
        }
    };

    const res = await fetch(`${API_BASE}/api/targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    if (!res.ok) {
        alert('Target setup failed');
        return;
    }

    hideTargetModal();
    e.target.reset();
    fetchNodes();
}

// ═══════════════════════════════════════════════════════════════
// Phase 6: Simulated Departments (Mock Databases)
// ═══════════════════════════════════════════════════════════════

async function fetchSimulatedState() {
    try {
        const response = await fetch(`${API_BASE}/mock/state`);
        const state = await response.json();
        
        Object.entries(state).forEach(([dept, records]) => {
            const container = document.getElementById(`${dept.toLowerCase()}DbContent`);
            if(!container) return;
            
            const entries = Object.entries(records);
            if(entries.length === 0) {
                container.innerHTML = `<p class="text-muted text-center">No records in ${dept}.</p>`;
            } else {
                container.innerHTML = entries.map(([id, data]) => `
                    <div class="db-record-card">
                        <div class="record-id-row">
                            <span class="record-id">${id}</span>
                            <button class="btn-text" onclick="openMockEditModal('${dept}', '${id}', ${JSON.stringify(data).replace(/"/g, '&quot;')})">Edit</button>
                        </div>
                        <pre class="record-data">${JSON.stringify(data, null, 2)}</pre>
                    </div>
                `).join('');
            }
        });
    } catch(e) { console.error("Failed to fetch mock state", e); }
}

function openMockEditModal(system, ubid, data) {
    document.getElementById('editSystem').value = system;
    document.getElementById('editUbid').value = ubid;
    const container = document.getElementById('editFieldsContainer');
    container.innerHTML = '';
    
    Object.entries(data).forEach(([key, value]) => {
        const div = document.createElement('div');
        div.className = 'form-group';
        div.innerHTML = `<label>${key}</label><input type="text" name="${key}" value="${value}">`;
        container.appendChild(div);
    });
    
    document.getElementById('mockEditModal').classList.add('active');
}

function hideMockEditModal() {
    document.getElementById('mockEditModal').classList.remove('active');
}

async function handleMockEditSubmit(e) {
    e.preventDefault();
    const system = document.getElementById('editSystem').value;
    const ubid = document.getElementById('editUbid').value;
    const formData = new FormData(e.target);
    const updatedData = {};
    formData.forEach((value, key) => updatedData[key] = value);

    try {
        // 1. Update the Mock Database
        await fetch(`${API_BASE}/mock/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system, ubid, data: updatedData })
        });

        // 2. Trigger Fabric Ingestion (Webhook)
        // We simulate the system pushing its change to the Fabric
        await fetch(`${API_BASE}/api/ingest/webhook`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_system: system,
                entity_type: "FACTORY",
                entity_id: ubid,
                changes: Object.entries(updatedData).map(([k, v]) => ({ field: k, new: v })),
                timestamp: new Date().toISOString()
            })
        });

        hideMockEditModal();
        fetchSimulatedState();
        fetchEvents(); // Update dashboard
    } catch(err) { alert("Update failed"); }
}

// ═══════════════════════════════════════════════════════════════
// Phase 7: Modals & Initialization
// ═══════════════════════════════════════════════════════════════

function showAddConnectorModal() { document.getElementById('connectorModal').classList.add('active'); }
function hideConnectorModal() { document.getElementById('connectorModal').classList.remove('active'); }
function showAddTargetModal() { document.getElementById('targetModal').classList.add('active'); }
function hideTargetModal() { document.getElementById('targetModal').classList.remove('active'); }

document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchEvents();
    
    document.getElementById('sandboxForm')?.addEventListener('submit', handleSandboxSubmit);
    document.getElementById('fileUploadForm')?.addEventListener('submit', handleFileUpload);
    document.getElementById('mockEditForm')?.addEventListener('submit', handleMockEditSubmit);
    document.getElementById('connectorForm')?.addEventListener('submit', handleConnectorSubmit);
    document.getElementById('targetForm')?.addEventListener('submit', handleTargetSubmit);
    
    setInterval(() => {
        const activeTab = document.querySelector('.nav-links button.active')?.getAttribute('onclick')?.match(/'([^']+)'/)?.[1];
        if(activeTab) showTab(activeTab);
    }, 5000);
});

document.addEventListener('DOMContentLoaded', () => {
    const backendUrl = 'http://127.0.0.1:5000';
    const accessToken = localStorage.getItem('access_token');
    
    // Redirect if no token
    if (!accessToken) {
        window.location.href = '../auth/index.html';
        return;
    }

    // DOM Elements
    const liveCameraGrid = document.getElementById('liveCameraGrid');
    const alertHistoryTableBody = document.getElementById('alertHistoryTableBody');
    const globalGauge = document.getElementById('globalGauge');
    const globalThreatValue = document.getElementById('globalThreatValue');
    const threatLabel = document.getElementById('threatLabel');
    const factorText = document.getElementById('factorText');
    const learningToggle = document.getElementById('learningToggle');
    const userNameElement = document.getElementById('userName');

    let trendChart = null;
    let cameras = [];

    // Set User Name
    userNameElement.textContent = localStorage.getItem('user_name') || 'Operator';

    // --- Logout ---
    document.getElementById('logoutBtn').addEventListener('click', () => {
        localStorage.removeItem('access_token');
        window.location.href = '../auth/index.html';
    });

    // --- Authenticated Fetch ---
    async function apiFetch(endpoint, options = {}) {
        const currentToken = localStorage.getItem('access_token');
        console.log(`[DEBUG] Attempting fetch: ${endpoint}`);
        console.log(`[DEBUG] Token from storage: ${currentToken ? "Found (starts with " + currentToken.substring(0, 10) + "...)" : "MISSING"}`);

        if (!options.headers) options.headers = {};
        
        if (currentToken) {
            options.headers['Authorization'] = `Bearer ${currentToken}`;
        }
        options.headers['Content-Type'] = 'application/json';

        console.log(`[DEBUG] Headers being sent:`, JSON.stringify(options.headers));

        try {
            const res = await fetch(`${backendUrl}${endpoint}`, options);
            console.log(`[DEBUG] Response status: ${res.status}`);
            if (res.status === 401 || res.status === 422) {
                window.location.href = '../auth/index.html';
                return null;
            }
            return res.ok ? await res.json() : null;
        } catch (err) {
            console.error(`Fetch error: ${endpoint}`, err);
            return null;
        }
    }

    // --- Learning Mode ---
    async function initLearningMode() {
        const data = await apiFetch('/api/settings/learning-mode');
        if (data) learningToggle.checked = data.enabled;
    }

    learningToggle.addEventListener('change', async () => {
        await apiFetch('/api/settings/learning-mode', {
            method: 'POST',
            body: JSON.stringify({ enabled: learningToggle.checked })
        });
    });

    // --- Camera Grid ---
    async function fetchCameras() {
        const data = await apiFetch('/api/cameras/live');
        if (!data) {
            liveCameraGrid.innerHTML = '<div style="color: var(--danger); padding: 20px;">Failed to fetch live cameras. Please check connection.</div>';
            return;
        }
        cameras = data;
        liveCameraGrid.innerHTML = '';
        
        if (cameras.length === 0) {
            liveCameraGrid.innerHTML = '<div style="color: var(--text-dim); padding: 20px;">No active cameras found.</div>';
            return;
        }

        cameras.forEach(cam => {
            const card = document.createElement('div');
            card.className = 'camera-card';
            
            const level = (cam.threat_level || 'NORMAL').toLowerCase();
            const score = cam.threat_score || 0;
            const behavior = cam.behavior || 'initializing';

            card.innerHTML = `
                <div class="cam-header">
                    <span class="cam-name">${cam.name}</span>
                    <span style="font-size: 0.7rem; color: var(--text-dim)">${(cam.zone || 'general').toUpperCase()}</span>
                </div>
                <div class="cam-feed">
                    <img src="${backendUrl}/api/cameras/stream/${cam.id}" id="feed-${cam.id}" onerror="this.src='https://via.placeholder.com/640x480?text=Camera+Disconnected'">
                    <div class="cam-overlay">
                        <div class="behavior-badge">
                            <i class="fas fa-user-shield"></i>
                            <span id="behavior-${cam.id}">${behavior}</span>
                        </div>
                        <div class="threat-bar-wrap">
                            <div class="threat-bar" id="bar-${cam.id}" style="width: ${score}%; background: var(--${level})"></div>
                        </div>
                    </div>
                </div>
            `;
            liveCameraGrid.appendChild(card);
        });
    }

    // --- Alerts Table ---
    window.fetchAlerts = async function() {
        const alerts = await apiFetch('/api/alerts/recent?limit=20');
        if (!alerts) {
            alertHistoryTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--danger); padding: 20px;">Failed to fetch alerts.</td></tr>';
            return;
        }
        
        alertHistoryTableBody.innerHTML = '';
        if (alerts.length === 0) {
            alertHistoryTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px;">No recent alerts.</td></tr>';
            return;
        }

        alerts.forEach(alert => {
            const date = new Date(alert.timestamp).toLocaleTimeString();
            const levelClass = `score-${alert.threat_level.toLowerCase()}`;
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><span class="level-dot" style="background: var(--${alert.threat_level.toLowerCase()})"></span>${alert.threat_level}</td>
                <td>${date}</td>
                <td>${alert.camera_name || 'CAM'}</td>
                <td>${alert.behavior}</td>
                <td class="${levelClass}" style="font-weight:bold">${alert.threat_score}</td>
                <td>
                    <button class="btn-action" onclick="window.openAlert(${alert.id})"><i class="fas fa-eye"></i></button>
                    <button class="btn-action btn-dismiss" onclick="window.dismissAlert(${alert.id})"><i class="fas fa-check"></i></button>
                </td>
            `;
            alertHistoryTableBody.appendChild(row);
        });
    };

    window.dismissAlert = async (id) => {
        const res = await apiFetch(`/api/alerts/${id}/dismiss`, { method: 'POST' });
        if (res) fetchAlerts();
    };

    // --- Threat Gauge & Chart ---
    function updateGauge(score, level, breakdown) {
        const degrees = (score / 100) * 180;
        globalGauge.style.transform = `rotate(${degrees}deg)`;
        globalGauge.style.borderColor = `var(--${level.toLowerCase()})`;
        globalThreatValue.textContent = score;
        globalThreatValue.className = `gauge-value score-${level.toLowerCase()}`;
        
        threatLabel.textContent = level === 'NORMAL' ? 'SYSTEM SECURE' : `THREAT DETECTED: ${level}`;
        threatLabel.className = `status-label score-${level.toLowerCase()}`;
        
        if (breakdown) {
            factorText.textContent = `Base ${breakdown.base} × Context ${breakdown.context} × Novelty ${breakdown.novelty} = ${score}`;
        }
    }

    async function initChart() {
        const ctx = document.getElementById('trendChart').getContext('2d');
        const data = await apiFetch('/api/alerts/trend') || [];
        
        trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.map(d => d.time),
                datasets: [{
                    label: 'Threat Score',
                    data: data.map(d => d.score),
                    borderColor: '#3b82f6',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    backgroundColor: 'rgba(59, 130, 246, 0.1)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { 
                    x: { display: false },
                    y: { beginAtZero: true, max: 100, display: false }
                }
            }
        });
    }

    // --- WebSockets ---
    const socket = io(backendUrl);
    socket.on('camera_live_update', (data) => {
        const behaviorEl = document.getElementById(`behavior-${data.camera_id}`);
        const barEl = document.getElementById(`bar-${data.camera_id}`);
        
        if (behaviorEl) behaviorEl.textContent = data.behavior;
        if (barEl) {
            barEl.style.width = `${data.threat_score}%`;
            const level = data.threat_level.toLowerCase();
            barEl.style.background = `var(--${level})`;
        }

        // Update Global UI if this is a high threat
        if (data.threat_score > 30) {
            updateGauge(data.threat_score, data.threat_level, {
                base: data.base_score || 0.1,
                context: data.context_multiplier || 1.0,
                novelty: data.novelty_factor || 1.0
            });
        }
    });

    socket.on('new_alert', () => fetchAlerts());

    // --- Init ---
    async function init() {
        await fetchCameras();
        await fetchAlerts();
        await initChart();
        await initLearningMode();
    }

    init();
    setInterval(window.fetchAlerts, 30000); // Auto refresh
});

const API_BASE_URL = '/api/sources';
const STREAM_BASE_URL = '/api/stream';
const TRIPWIRE_BASE_URL = '/api/tripwires';

// State
let sources = [];
let currentTripwire = {
    source_id: null,
    x1: 0, y1: 0.5,
    x2: 1, y2: 0.5,
    direction: 'IN'
};
let isDrawing = false;
let dragNode = null; // 'start', 'end', or null

// DOM Elements
const sourcesList = document.getElementById('sources-list');
const uploadForm = document.getElementById('upload-form');
const rtspForm = document.getElementById('rtsp-form');
const notification = document.getElementById('notification');
const previewModal = document.getElementById('preview-modal');
const videoWrapper = document.getElementById('video-wrapper');
const modalTitle = document.getElementById('modal-title');

// Tripwire Elements
const tripwireModal = document.getElementById('tripwire-modal');
const tripwireCanvas = document.getElementById('tripwire-canvas');
const canvasWrapper = document.getElementById('canvas-wrapper');
const canvasLoading = document.getElementById('canvas-loading');
const ctx = tripwireCanvas.getContext('2d');
let backgroundImage = new Image();

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log('App initialization started...');
    fetchSources();
    setupNavigation();
    setupCanvasListeners();
    console.log('App initialization complete.');
});

// --- Navigation & View Switching ---
function setupNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const view = link.getAttribute('data-view');

            // Update active link
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            // Switch views
            document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
            document.getElementById(`${view}-view`).classList.remove('hidden');

            // Update title
            document.getElementById('view-title').innerText = view === 'management' ? 'Módulo de Gestión' : 'Módulo de Visualización';
        });
    });
}

function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`.tab-btn[onclick="switchTab('${tab}')"]`).classList.add('active');

    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`${tab}-ingest`).classList.add('active');
}

// --- API Calls ---

async function fetchSources() {
    try {
        const response = await fetch(API_BASE_URL);
        const data = await response.json();
        // Ordenar por tipo: primero 'file', luego 'rtsp', alfabéticamente si es otro
        sources = data.sort((a, b) => {
            if (a.type === 'file' && b.type !== 'file') return -1;
            if (a.type !== 'file' && b.type === 'file') return 1;
            return a.type.localeCompare(b.type);
        });
        renderSources();
    } catch (error) {
        showNotification('Error al cargar las fuentes', 'error');
    }
}

function renderSources() {
    if (sources.length === 0) {
        sourcesList.innerHTML = '<div class="placeholder-text">No hay fuentes registradas.</div>';
        return;
    }

    console.log('Rendering sources:', sources);
    sourcesList.innerHTML = sources.map(source => `
        <div class="source-item">
            <div class="source-info">
                <h4>${source.name} <span class="badge badge-${source.type}">${source.type}</span></h4>
                <p>${source.path_url}</p>
            </div>
            <div class="source-actions">
                <button class="btn-schedule ${source.is_scheduled ? 'active-schedule' : ''}" onclick="openScheduleConfig(${source.id})" title="${source.is_scheduled ? 'Horario Activo' : 'Configurar Horario'}">
                    <i class="far fa-clock"></i> Schedule
                </button>
                <button class="btn-tripwire" onclick="openTripwireConfig(${source.id})">
                    <i class="fas fa-draw-polygon"></i> Tripwire
                </button>
                <button class="btn-preview" onclick="openPreview(${source.id})">
                    <i class="fas fa-play"></i>
                </button>
                <button class="btn-delete" onclick="deleteSource(${source.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// --- Upload & Drag-and-Drop Handling ---
const fileInput = document.getElementById('video-file');
const fileNameDisplay = document.getElementById('file-name-display');
const dropZone = document.getElementById('drop-zone');
const progressContainer = document.getElementById('upload-progress-container');
const progressBar = document.getElementById('upload-progress-bar');
const progressText = document.getElementById('upload-progress-text');
const uploadBtn = uploadForm.querySelector('button[type="submit"]');

// File Selection
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        fileNameDisplay.innerText = e.target.files[0].name;
    } else {
        fileNameDisplay.innerText = 'Click para subir o arrastra aquí';
    }
});

// Drag and Drop Effects
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('highlight'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('highlight'), false);
});

dropZone.addEventListener('drop', (e) => {
    let dt = e.dataTransfer;
    let files = dt.files;

    if (files.length > 0) {
        fileInput.files = files; // Assign files to input
        fileNameDisplay.innerText = files[0].name;
    }
}, false);

// Form Submit with Progress
uploadForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!fileInput.files.length) return;

    const formData = new FormData(uploadForm);

    // UI Setup
    progressContainer.classList.remove('hidden');
    uploadBtn.disabled = true;
    uploadBtn.innerText = 'Subiendo...';
    progressBar.style.width = '0%';
    progressText.innerText = '0%';

    const xhr = new XMLHttpRequest();

    // Progress Event
    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            progressBar.style.width = percentComplete + '%';
            progressText.innerText = percentComplete + '%';
            if (percentComplete === 100) {
                progressText.innerText = 'Procesando archivo...';
            }
        }
    });

    // Completion Event
    xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
            showNotification('Archivo subido con éxito', 'success');
            uploadForm.reset();
            fileNameDisplay.innerText = 'Click para subir o arrastra aquí';
            fetchSources();
        } else {
            showNotification('Error al subir el archivo', 'error');
        }
        resetUploadUI();
    });

    // Error Event
    xhr.addEventListener('error', () => {
        showNotification('Error de conexión', 'error');
        resetUploadUI();
    });

    xhr.open('POST', `${API_BASE_URL}/upload`);
    xhr.send(formData);
});

function resetUploadUI() {
    progressContainer.classList.add('hidden');
    uploadBtn.disabled = false;
    uploadBtn.innerText = 'Subir Fuente';
    progressBar.style.width = '0%';
}

rtspForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(rtspForm);
    const data = {
        name: formData.get('name'),
        path_url: formData.get('path_url'),
        type: 'rtsp'
    };

    try {
        const response = await fetch(`${API_BASE_URL}/rtsp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showNotification('Cámara RTSP registrada', 'success');
            rtspForm.reset();
            fetchSources();
        } else {
            showNotification('Error al registrar la cámara', 'error');
        }
    } catch (error) {
        showNotification('Error de conexión', 'error');
    }
});

async function deleteSource(id) {
    if (!confirm('¿Estás seguro de eliminar esta fuente?')) return;

    try {
        const response = await fetch(`${API_BASE_URL}/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showNotification('Fuente eliminada', 'success');
            fetchSources();
        } else {
            showNotification('Error al eliminar la fuente', 'error');
        }
    } catch (error) {
        showNotification('Error de conexión', 'error');
    }
}

// --- Video Preview ---


function openPreview(id) {
    const source = sources.find(s => s.id === id);
    if (!source) return;

    modalTitle.innerText = `Reproduciendo: ${source.name}`;
    videoWrapper.innerHTML = ''; // Clear previous content

    const startTime = Date.now();

    // Indicador UI para la Métrica Frontend
    const loadingDiv = document.createElement('div');
    loadingDiv.style.position = 'absolute';
    loadingDiv.style.top = '50%';
    loadingDiv.style.left = '50%';
    loadingDiv.style.transform = 'translate(-50%, -50%)';
    loadingDiv.style.color = 'white';
    loadingDiv.style.backgroundColor = 'rgba(0,0,0,0.8)';
    loadingDiv.style.padding = '15px 25px';
    loadingDiv.style.borderRadius = '8px';
    loadingDiv.style.zIndex = '100';
    loadingDiv.style.fontSize = '18px';
    loadingDiv.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i> Solicitando video...`;

    videoWrapper.style.position = 'relative';
    videoWrapper.appendChild(loadingDiv);

    if (source.type === 'rtsp' || source.type === 'file') {
        const img = document.createElement('img');
        img.src = `${STREAM_BASE_URL}/${source.type}/${id}?t=${startTime}`;
        img.alt = `${source.type.toUpperCase()} Stream`;
        img.className = 'w-full h-auto object-contain bg-black';
        img.style.opacity = '0';

        img.onload = () => {
            const endTime = Date.now();
            const totalFrontendDelay = ((endTime - startTime) / 1000).toFixed(2);
            console.log(`[FRONTEND METRICA] Tiempo total desde Clic hasta 1er Frame: ${totalFrontendDelay} seg`);

            fetch('/api/stream/metrics', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_id: source.id,
                    camera_name: source.name,
                    load_time_sec: parseFloat(totalFrontendDelay)
                })
            }).catch(err => console.error("Error logging metrics", err));

            if (loadingDiv.parentNode) {
                loadingDiv.style.backgroundColor = 'rgba(0, 128, 0, 0.8)';
                loadingDiv.innerHTML = `<i class="fas fa-check mr-2"></i> Cargado en: ${totalFrontendDelay} seg`;
                setTimeout(() => { if (loadingDiv.parentNode) loadingDiv.remove(); }, 4000);
            }
            img.style.opacity = '1';
        };

        img.onerror = () => {
            if (loadingDiv.parentNode) {
                loadingDiv.style.backgroundColor = 'rgba(255, 0, 0, 0.8)';
                loadingDiv.innerHTML = `<i class="fas fa-exclamation-triangle mr-2"></i> Error de conexión.`;
            }
        };

        videoWrapper.appendChild(img);
    }

    previewModal.classList.add('active');
}

function closeModal(type) {
    if (type === 'preview') {
        const img = videoWrapper.querySelector('img');
        if (img) img.src = '';
        const vid = videoWrapper.querySelector('video');
        if (vid) vid.srcObject = null;

        previewModal.classList.remove('active');
        videoWrapper.innerHTML = '';
    } else if (type === 'tripwire') {
        tripwireModal.classList.remove('active');
    } else if (type === 'schedule') {
        document.getElementById('schedule-modal').classList.remove('active');
    }
}

// --- Schedule Logic ---
async function openScheduleConfig(id) {
    const source = sources.find(s => s.id === id);
    if (!source) return;

    document.getElementById('schedule-modal-title').innerText = `Horario: ${source.name}`;
    document.getElementById('schedule-source-id').value = id;
    const modal = document.getElementById('schedule-modal');
    modal.classList.add('active');

    try {
        const response = await fetch(`/api/schedules/${id}`);
        if (response.ok) {
            const data = await response.json();
            document.getElementById('schedule-active').checked = data.is_active;
            document.getElementById('sch-mon').checked = data.monday;
            document.getElementById('sch-tue').checked = data.tuesday;
            document.getElementById('sch-wed').checked = data.wednesday;
            document.getElementById('sch-thu').checked = data.thursday;
            document.getElementById('sch-fri').checked = data.friday;
            document.getElementById('sch-sat').checked = data.saturday;
            document.getElementById('sch-sun').checked = data.sunday;
            document.getElementById('schedule-start').value = data.start_time;
            document.getElementById('schedule-end').value = data.end_time;
        } else {
            showNotification('Error obteniendo horario, usando por defecto', 'error');
        }
    } catch (error) {
        console.error('API Error:', error);
    }
}

document.getElementById('schedule-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('schedule-source-id').value;

    const payload = {
        source_id: parseInt(id),
        is_active: document.getElementById('schedule-active').checked,
        monday: document.getElementById('sch-mon').checked,
        tuesday: document.getElementById('sch-tue').checked,
        wednesday: document.getElementById('sch-wed').checked,
        thursday: document.getElementById('sch-thu').checked,
        friday: document.getElementById('sch-fri').checked,
        saturday: document.getElementById('sch-sat').checked,
        sunday: document.getElementById('sch-sun').checked,
        start_time: document.getElementById('schedule-start').value,
        end_time: document.getElementById('schedule-end').value
    };

    try {
        const response = await fetch(`/api/schedules/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            showNotification('Horario guardado correctamente', 'success');
            closeModal('schedule');
            fetchSources(); // Recharge list to update colors
        } else {
            showNotification('Error al guardar el horario', 'error');
        }
    } catch (error) {
        showNotification('Error de conexión', 'error');
    }
});

// --- Tripwire Logic ---

async function openTripwireConfig(id) {
    const source = sources.find(s => s.id === id);
    if (!source) return;

    console.log(`Configuring tripwire for source ${id} (${source.name})`);

    // Reset state to defaults for this specific ID
    currentTripwire = {
        source_id: id,
        x1: 0.2, y1: 0.5,
        x2: 0.8, y2: 0.5,
        direction: 'IN'
    };

    tripwireModal.classList.add('active');
    canvasLoading.style.display = 'flex';

    try {
        // 1. Fetch tripwire if exists
        const twResponse = await fetch(`${TRIPWIRE_BASE_URL}/source/${id}`);
        if (twResponse.ok) {
            const data = await twResponse.json();
            console.log('Existing tripwire found:', data);
            // Merge with current state but ensure source_id is strictly the current one
            currentTripwire = { ...currentTripwire, ...data, source_id: id };
        } else {
            console.log('No existing tripwire found, using defaults.');
        }

        updateDirectionUI();

        // 2. Fetch frame for background
        backgroundImage = new Image();
        backgroundImage.onload = () => {
            canvasLoading.style.display = 'none';
            resizeCanvas();
            draw();
        };
        backgroundImage.src = `${TRIPWIRE_BASE_URL}/frame/${id}?t=${Date.now()}`;
    } catch (error) {
        console.error('Error loading tripwire:', error);
        showNotification('Error al cargar configuración de tripwire', 'error');
        canvasLoading.style.display = 'none';
    }
}

function resizeCanvas() {
    const wrapper = canvasWrapper;
    tripwireCanvas.width = wrapper.clientWidth;
    tripwireCanvas.height = wrapper.clientHeight;
}

function draw() {
    if (!backgroundImage.complete) return;

    ctx.clearRect(0, 0, tripwireCanvas.width, tripwireCanvas.height);

    // Draw background image
    ctx.drawImage(backgroundImage, 0, 0, tripwireCanvas.width, tripwireCanvas.height);

    const x1 = currentTripwire.x1 * tripwireCanvas.width;
    const y1 = currentTripwire.y1 * tripwireCanvas.height;
    const x2 = currentTripwire.x2 * tripwireCanvas.width;
    const y2 = currentTripwire.y2 * tripwireCanvas.height;

    // Draw tripwire line
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = '#10b981';
    ctx.lineWidth = 4;
    ctx.shadowBlur = 10;
    ctx.shadowColor = 'rgba(16, 185, 129, 0.5)';
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Draw handles (nodes)
    drawNode(x1, y1, dragNode === 'start');
    drawNode(x2, y2, dragNode === 'end');

    // Draw direction arrow
    drawDirectionArrow(x1, y1, x2, y2);
}

function drawNode(x, y, active) {
    ctx.beginPath();
    ctx.arc(x, y, active ? 10 : 7, 0, Math.PI * 2);
    ctx.fillStyle = active ? '#fff' : '#10b981';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();
}

function drawDirectionArrow(x1, y1, x2, y2) {
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;

    const angle = Math.atan2(y2 - y1, x2 - x1);
    const sign = currentTripwire.direction === 'IN' ? -1 : 1;

    ctx.save();
    ctx.translate(midX, midY);
    ctx.rotate(angle);

    // Arrow pointing perpendicular from the line
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, sign * 30);
    ctx.strokeStyle = '#6366f1';
    ctx.lineWidth = 3;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(-10, sign * 20);
    ctx.lineTo(0, sign * 30);
    ctx.lineTo(10, sign * 20);
    ctx.fillStyle = '#6366f1';
    ctx.fill();

    ctx.restore();
}

function setupCanvasListeners() {
    tripwireCanvas.addEventListener('mousedown', (e) => {
        const pos = getMousePos(e);
        const startDist = getDist(pos, { x: currentTripwire.x1 * tripwireCanvas.width, y: currentTripwire.y1 * tripwireCanvas.height });
        const endDist = getDist(pos, { x: currentTripwire.x2 * tripwireCanvas.width, y: currentTripwire.y2 * tripwireCanvas.height });

        if (startDist < 20) dragNode = 'start';
        else if (endDist < 20) dragNode = 'end';
        else {
            // Start a new line
            currentTripwire.x1 = pos.x / tripwireCanvas.width;
            currentTripwire.y1 = pos.y / tripwireCanvas.height;
            currentTripwire.x2 = currentTripwire.x1;
            currentTripwire.y2 = currentTripwire.y1;
            dragNode = 'end';
        }
        draw();
    });

    window.addEventListener('mousemove', (e) => {
        if (!dragNode) return;
        const pos = getMousePos(e);

        if (dragNode === 'start') {
            currentTripwire.x1 = Math.max(0, Math.min(1, pos.x / tripwireCanvas.width));
            currentTripwire.y1 = Math.max(0, Math.min(1, pos.y / tripwireCanvas.height));
        } else {
            currentTripwire.x2 = Math.max(0, Math.min(1, pos.x / tripwireCanvas.width));
            currentTripwire.y2 = Math.max(0, Math.min(1, pos.y / tripwireCanvas.height));
        }
        draw();
    });

    window.addEventListener('mouseup', () => {
        dragNode = null;
        draw();
    });
}

function getMousePos(e) {
    const rect = tripwireCanvas.getBoundingClientRect();
    return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };
}

function getDist(p1, p2) {
    return Math.sqrt(Math.pow(p1.x - p2.x, 2) + Math.pow(p1.y - p2.y, 2));
}

function setDirection(dir) {
    currentTripwire.direction = dir;
    updateDirectionUI();
    draw();
}

function updateDirectionUI() {
    document.getElementById('dir-in-btn').classList.toggle('active', currentTripwire.direction === 'IN');
    document.getElementById('dir-out-btn').classList.toggle('active', currentTripwire.direction === 'OUT');
}

function resetTripwire() {
    currentTripwire.x1 = 0.2;
    currentTripwire.y1 = 0.5;
    currentTripwire.x2 = 0.8;
    currentTripwire.y2 = 0.5;
    draw();
}

async function saveTripwire() {
    try {
        const response = await fetch(TRIPWIRE_BASE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentTripwire)
        });

        if (response.ok) {
            showNotification('Configuración guardada correctamente', 'success');
            tripwireModal.classList.remove('active');
        } else {
            showNotification('Error al guardar configuración', 'error');
        }
    } catch (error) {
        showNotification('Error de conexión', 'error');
    }
}

// --- UI Utilities ---

function showNotification(message, type) {
    notification.innerText = message;
    notification.className = `notification active ${type}`;

    setTimeout(() => {
        notification.classList.remove('active');
    }, 3000);
}

// Close modals when clicking outside
window.onclick = (event) => {
    if (event.target == previewModal) {
        closeModal('preview');
    }
    if (event.target == tripwireModal) {
        closeModal('tripwire');
    }
    if (event.target == document.getElementById('schedule-modal')) {
        closeModal('schedule');
    }
}

// --- Dashboard Logic ---

// Chart Instances
let timeSeriesChartInstance = null;
let locationsChartInstance = null;
let periodsChartInstance = null;
let accumulatedChartInstance = null;

// Initialize Dashboard UI & Charts
function initDashboard() {
    console.log("Initializing Dashboard...");
    // 1. Populate Filters
    // Dates (default to last 7 days)
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 7);

    document.getElementById('filter-end-date').valueAsDate = end;
    document.getElementById('filter-start-date').valueAsDate = start;

    // Cameras
    const cameraSelect = document.getElementById('filter-cameras');
    cameraSelect.innerHTML = '';
    sources.forEach(src => {
        const option = document.createElement('option');
        option.value = src.id;
        option.text = src.name;
        cameraSelect.appendChild(option);
    });

    // 2. Initial Setup for Charts
    setupChartsBase();

    // 3. Load initial data
    updateDashboard();
}

function setupChartsBase() {
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = 'Inter';
    const gridColor = 'rgba(255, 255, 255, 0.05)';

    const timeCtx = document.getElementById('timeSeriesChart').getContext('2d');
    timeSeriesChartInstance = new Chart(timeCtx, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { grid: { color: gridColor }, title: { display: true, text: 'Fechas' } },
                y: { grid: { color: gridColor }, beginAtZero: true, title: { display: true, text: 'Tráfico' } }
            },
            plugins: { tooltip: { enabled: true }, legend: { position: 'top' } },
            elements: {
                line: { tension: 0.4, borderWidth: 3 },
                point: { radius: 3, hitRadius: 10, hoverRadius: 6 }
            }
        }
    });

    const locCtx = document.getElementById('locationsChart').getContext('2d');
    locationsChartInstance = new Chart(locCtx, {
        type: 'bar',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y', // Horizontal bars for locations
            scales: {
                x: { grid: { color: gridColor }, beginAtZero: true },
                y: { grid: { display: false } }
            },
            plugins: { legend: { position: 'bottom' } },
            elements: { bar: { borderRadius: 6 } }
        }
    });

    const perCtx = document.getElementById('periodsChart').getContext('2d');
    periodsChartInstance = new Chart(perCtx, {
        type: 'bar',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { display: false } },
                y: { grid: { color: gridColor }, beginAtZero: true }
            },
            plugins: { legend: { display: true, position: 'bottom' } },
            elements: { bar: { borderRadius: 8, maxBarThickness: 50 } }
        }
    });

    const accCtx = document.getElementById('accumulatedChart').getContext('2d');
    accumulatedChartInstance = new Chart(accCtx, {
        type: 'bar',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { display: false } },
                y: { grid: { color: gridColor }, beginAtZero: true }
            },
            plugins: { legend: { display: false } },
            elements: { bar: { borderRadius: 6, maxBarThickness: 40 } }
        }
    });
}

function getFilterParams() {
    const startDate = document.getElementById('filter-start-date').value;
    const endDate = document.getElementById('filter-end-date').value;

    const cameraSelect = document.getElementById('filter-cameras');
    const selectedCameras = Array.from(cameraSelect.selectedOptions).map(opt => opt.value);

    const slotSelect = document.getElementById('filter-timeslots');
    const selectedSlots = Array.from(slotSelect.selectedOptions).map(opt => opt.value);

    return {
        start_date: startDate,
        end_date: endDate,
        cameras: selectedCameras.join(','),
        time_slots: selectedSlots.join(',')
    };
}

async function updateDashboard() {
    const params = getFilterParams();

    if (!params.start_date || !params.end_date) {
        showNotification('Debe seleccionar fechas válidas', 'error');
        return;
    }

    // Show Loading Skeleton
    const dataContainer = document.getElementById('dashboard-data');
    const emptyContainer = document.getElementById('dashboard-empty');
    const loadContainer = document.getElementById('dashboard-loading');

    if (dataContainer && loadContainer && emptyContainer) {
        dataContainer.classList.add('hidden');
        emptyContainer.classList.add('hidden');
        loadContainer.classList.remove('hidden');
    }

    const queryParams = new URLSearchParams(params).toString();
    try {
        const response = await fetch(`/api/analytics/dashboard?${queryParams}`);
        if (!response.ok) throw new Error("Error fetching data");
        const data = await response.json();

        // Check for Empty State
        const isDataEmpty = data.kpis.total_in === 0 && data.kpis.total_out === 0;

        if (dataContainer && loadContainer && emptyContainer) {
            loadContainer.classList.add('hidden');
            if (isDataEmpty) {
                emptyContainer.classList.remove('hidden');
            } else {
                dataContainer.classList.remove('hidden');
                renderDashboardData(data);

                // Update Last Updated Timestamp
                const now = new Date();
                const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const lastUpdatedEl = document.getElementById('last-updated');
                if (lastUpdatedEl) {
                    lastUpdatedEl.innerText = `Última actualización: ${timeStr}`;
                }
            }
        } else {
            renderDashboardData(data);
        }

        showNotification('Dashboard actualizado', 'success');
    } catch (error) {
        console.error(error);
        if (loadContainer && dataContainer) {
            loadContainer.classList.add('hidden');
            dataContainer.classList.remove('hidden');
        }
        showNotification('Error actualizando dashboard', 'error');
    }
}

function clearFilters() {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 7);

    document.getElementById('filter-end-date').valueAsDate = end;
    document.getElementById('filter-start-date').valueAsDate = start;

    const cameraSelect = document.getElementById('filter-cameras');
    Array.from(cameraSelect.options).forEach(opt => opt.selected = false);

    const slotSelect = document.getElementById('filter-timeslots');
    Array.from(slotSelect.options).forEach(opt => opt.selected = false);

    updateDashboard();
}

function renderDashboardData(data) {
    // 1. KPI Cards
    const safeFormat = (val) => {
        if (val === undefined || val === null) return '0';
        // Add thousands separator for better readability
        return Number(val).toLocaleString('es-ES');
    };

    document.getElementById('kpi-total-in').innerText = safeFormat(data.kpis.total_in);
    document.getElementById('kpi-total-out').innerText = safeFormat(data.kpis.total_out);
    document.getElementById('kpi-avg-occupancy').innerText = safeFormat(data.kpis.aforo_promedio);

    let rate = data.kpis.stay_rate !== undefined ? `${data.kpis.stay_rate.toLocaleString('es-ES')}%` : '0%';
    document.getElementById('kpi-stay-rate').innerText = rate;

    // Trend Indicators
    function updateTrend(id, val) {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = 'trend-indicator'; // reset base class
        if (val > 0) {
            el.innerHTML = `<i class="fas fa-arrow-up"></i> ${val}% vs ant.`;
            el.classList.add('positive');
        } else if (val < 0) {
            el.innerHTML = `<i class="fas fa-arrow-down"></i> ${Math.abs(val)}% vs ant.`;
            el.classList.add('negative');
        } else {
            el.innerHTML = `<i class="fas fa-minus"></i> Sin cambios`;
            el.classList.add('neutral');
        }
    }

    if (data.kpis.trends) {
        updateTrend('trend-total-in', data.kpis.trends.total_in);
        updateTrend('trend-total-out', data.kpis.trends.total_out);
        updateTrend('trend-avg-occupancy', data.kpis.trends.aforo_promedio);
    }

    // 2. Charts
    const defaultColors = [
        { border: '#6366f1', bg: 'rgba(99, 102, 241, 0.2)' },
        { border: '#10b981', bg: 'rgba(16, 185, 129, 0.2)' },
        { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.2)' },
        { border: '#ef4444', bg: 'rgba(239, 68, 68, 0.2)' },
        { border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.2)' },
        { border: '#06b6d4', bg: 'rgba(6, 182, 212, 0.2)' }
    ];

    if (data.charts.time_series.datasets) {
        data.charts.time_series.datasets.forEach((ds, i) => {
            const colorObj = defaultColors[i % defaultColors.length];
            ds.borderColor = colorObj.border;
            ds.backgroundColor = colorObj.bg;
            ds.fill = true;
            ds.tension = 0.4; // Smooth lines
        });
        timeSeriesChartInstance.data = data.charts.time_series;
        timeSeriesChartInstance.update();
    }

    if (data.charts.compare_locations.datasets) {
        if (data.charts.compare_locations.datasets.length > 0) {
            data.charts.compare_locations.datasets[0].backgroundColor = 'rgba(16, 185, 129, 0.8)'; // IN
        }
        if (data.charts.compare_locations.datasets.length > 1) {
            data.charts.compare_locations.datasets[1].backgroundColor = 'rgba(239, 68, 68, 0.8)'; // OUT
        }
        locationsChartInstance.data = data.charts.compare_locations;
        locationsChartInstance.update();
    }

    if (data.charts.compare_periods.datasets) {
        data.charts.compare_periods.datasets.forEach((ds, i) => {
            ds.backgroundColor = i === 0 ? 'rgba(148, 163, 184, 0.6)' : 'rgba(99, 102, 241, 0.9)';
            ds.borderWidth = 0;
        });
        periodsChartInstance.data = data.charts.compare_periods;
        periodsChartInstance.update();
    }

    if (data.charts.accumulated.datasets) {
        if (data.charts.accumulated.datasets.length > 0) {
            // Gradient-like colors for days of week
            data.charts.accumulated.datasets[0].backgroundColor = [
                'rgba(245, 158, 11, 0.9)', 'rgba(217, 119, 6, 0.9)',
                'rgba(180, 83, 9, 0.9)', 'rgba(234, 88, 12, 0.9)',
                'rgba(194, 65, 12, 0.9)', 'rgba(99, 102, 241, 0.9)', 'rgba(79, 70, 229, 0.9)'
            ];
        }
        accumulatedChartInstance.data = data.charts.accumulated;
        accumulatedChartInstance.update();
    }
}

function downloadReport() {
    const params = getFilterParams();
    const queryParams = new URLSearchParams(params).toString();
    window.location.href = `/api/analytics/export?${queryParams}`;
}

// Hook navigation to initialize dashboard when first switched
const navLinks = document.querySelectorAll('.nav-link');
let dashboardInitialized = false;

navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        const view = link.getAttribute('data-view');
        if (view === 'visualization' && !dashboardInitialized && sources.length > 0) {
            initDashboard();
            dashboardInitialized = true;
        }
    });
});


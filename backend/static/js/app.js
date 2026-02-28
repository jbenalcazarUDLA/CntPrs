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

    // Both file and rtsp return MJPEG streams from stream.py
    // Append a timestamp to bypass browser caching of broken previous streams
    const img = document.createElement('img');
    img.src = `${STREAM_BASE_URL}/${source.type}/${id}?t=${startTime}`;
    img.alt = `${source.type.toUpperCase()} Stream`;
    // Add classes for better responsiveness if previous styles applied
    img.className = 'w-full h-auto object-contain bg-black';
    img.style.opacity = '0'; // Ocultar mientras carga

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

    previewModal.classList.add('active');
}

function closeModal(type) {
    if (type === 'preview') {
        const img = videoWrapper.querySelector('img');
        if (img) img.src = '';
        previewModal.classList.remove('active');
        videoWrapper.innerHTML = '';
    } else if (type === 'tripwire') {
        tripwireModal.classList.remove('active');
    }
}

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
}

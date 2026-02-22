// API Configuration
const API_BASE_URL = '/api/sources';
const STREAM_BASE_URL = '/api/stream';

// State
let sources = [];

// DOM Elements
const sourcesList = document.getElementById('sources-list');
const uploadForm = document.getElementById('upload-form');
const rtspForm = document.getElementById('rtsp-form');
const notification = document.getElementById('notification');
const previewModal = document.getElementById('preview-modal');
const videoWrapper = document.getElementById('video-wrapper');
const modalTitle = document.getElementById('modal-title');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    fetchSources();
    setupNavigation();
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
        sources = await response.json();
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

    sourcesList.innerHTML = sources.map(source => `
        <div class="source-item">
            <div class="source-info">
                <h4>${source.name} <span class="badge badge-${source.type}">${source.type}</span></h4>
                <p>${source.path_url}</p>
            </div>
            <div class="source-actions">
                <button class="btn-preview" onclick="openPreview(${source.id})">
                    <i class="fas fa-play"></i> Reproducir
                </button>
                <button class="btn-delete" onclick="deleteSource(${source.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(uploadForm);

    try {
        const response = await fetch(`${API_BASE_URL}/upload`, {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            showNotification('Archivo subido con éxito', 'success');
            uploadForm.reset();
            fetchSources();
        } else {
            showNotification('Error al subir el archivo', 'error');
        }
    } catch (error) {
        showNotification('Error de conexión', 'error');
    }
});

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

    if (source.type === 'file') {
        const video = document.createElement('video');
        video.src = `${STREAM_BASE_URL}/file/${id}`;
        video.controls = true;
        video.autoplay = true;
        videoWrapper.appendChild(video);
    } else if (source.type === 'rtsp') {
        const img = document.createElement('img');
        img.src = `${STREAM_BASE_URL}/rtsp/${id}`;
        img.alt = 'RTSP Stream';
        videoWrapper.appendChild(img);
    }

    previewModal.classList.add('active');
}

function closeModal() {
    previewModal.classList.remove('active');
    // Stop video/stream to save resources
    videoWrapper.innerHTML = '';
}

// Close modal when clicking outside
window.onclick = (event) => {
    if (event.target == previewModal) {
        closeModal();
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

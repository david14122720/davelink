/**
 * daveLinK — Frontend JavaScript
 */

// DOM Elements
const form = document.getElementById('shorten-form');
const urlInput = document.getElementById('url-input');
const submitBtn = document.getElementById('submit-btn');
const btnText = submitBtn.querySelector('.btn-text');
const btnLoading = submitBtn.querySelector('.btn-loading');

const resultSection = document.getElementById('result');
const shortUrlInput = document.getElementById('short-url');
const copyBtn = document.getElementById('copy-btn');
const qrBtn = document.getElementById('qr-btn');
const statsBtn = document.getElementById('stats-btn');

const qrSection = document.getElementById('qr-section');
const qrImage = document.getElementById('qr-image');
const qrOriginalUrl = document.getElementById('qr-original-url');
const closeQrBtn = document.getElementById('close-qr');
const downloadQrBtn = document.getElementById('download-qr');
const shareQrBtn = document.getElementById('share-qr');

const statsSection = document.getElementById('stats-section');
const totalClicks = document.getElementById('total-clicks');
const createdDate = document.getElementById('created-date');
const clicksList = document.getElementById('clicks-list');
const closeStatsBtn = document.getElementById('close-stats');

// QR Generator elements
const qrForm = document.getElementById('qr-form');
const qrUrlInput = document.getElementById('qr-url-input');
const qrGenerateBtn = document.getElementById('qr-generate-btn');
const qrGenerateText = qrGenerateBtn.querySelector('.btn-text');
const qrGenerateLoading = qrGenerateBtn.querySelector('.btn-loading');
const qrResult = document.getElementById('qr-result');
const qrResultImage = document.getElementById('qr-result-image');
const qrResultUrl = document.getElementById('qr-result-url');
const closeQrResultBtn = document.getElementById('close-qr-result');
const downloadQrResultBtn = document.getElementById('download-qr-result');
const copyQrResultBtn = document.getElementById('copy-qr-result');

// State
let currentCode = null;
let currentOriginalUrl = null;

// API Base URL
const API_BASE = '';

// Event Listeners
form.addEventListener('submit', handleSubmit);
copyBtn.addEventListener('click', handleCopy);
qrBtn.addEventListener('click', showQrSection);
statsBtn.addEventListener('click', showStatsSection);
closeQrBtn.addEventListener('click', () => qrSection.hidden = true);
closeStatsBtn.addEventListener('click', () => statsSection.hidden = true);
downloadQrBtn.addEventListener('click', handleDownloadQr);
shareQrBtn.addEventListener('click', handleShareQr);

// QR Generator event listeners
qrForm.addEventListener('submit', handleQrGenerate);
closeQrResultBtn.addEventListener('click', () => qrResult.hidden = true);
downloadQrResultBtn.addEventListener('click', handleDownloadQrResult);
copyQrResultBtn.addEventListener('click', handleCopyQrResult);

// Normalize URL: prepend https:// if no scheme present
function normalizeUrl(raw) {
    const trimmed = raw.trim();
    if (!trimmed) return trimmed;
    if (!/^https?:\/\//i.test(trimmed)) {
        return `https://${trimmed}`;
    }
    return trimmed;
}

// Handle form submission (shorten URL)
async function handleSubmit(e) {
    e.preventDefault();
    
    const url = normalizeUrl(urlInput.value);
    if (!url) return;
    urlInput.value = url;
    
    // Show loading state
    setLoading(true);
    hideError();
    
    try {
        const response = await fetch(`${API_BASE}/api/shorten`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url }),
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Error al acortar el enlace');
        }
        
        const data = await response.json();
        
        // Store current code and original URL
        currentCode = data.code;
        currentOriginalUrl = data.original_url;
        
        // Show result
        shortUrlInput.value = data.short_url;
        resultSection.hidden = false;
        
        // Hide other sections
        qrSection.hidden = true;
        statsSection.hidden = true;
        
    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

// Handle QR code generation (standalone)
async function handleQrGenerate(e) {
    e.preventDefault();
    
    const url = normalizeUrl(qrUrlInput.value);
    if (!url) return;
    qrUrlInput.value = url;
    
    // Show loading state
    qrGenerateText.hidden = true;
    qrGenerateLoading.hidden = false;
    qrGenerateBtn.disabled = true;
    
    try {
        // First, shorten the URL
        const shortenResponse = await fetch(`${API_BASE}/api/shorten`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url }),
        });
        
        if (!shortenResponse.ok) {
            const error = await shortenResponse.json();
            throw new Error(error.detail || 'Error al procesar el enlace');
        }
        
        const shortenData = await shortenResponse.json();
        
        // Then, get the QR code
        const qrResponse = await fetch(`${API_BASE}/api/qr/${shortenData.code}`);
        if (!qrResponse.ok) throw new Error('Error al generar QR');
        
        const qrData = await qrResponse.json();
        
        // Show QR result
        qrResultImage.src = `data:image/png;base64,${qrData.qr_code}`;
        qrResultUrl.textContent = url;
        qrResult.hidden = false;
        
        // Store for download
        qrResultImage.dataset.code = shortenData.code;
        qrResultImage.dataset.originalUrl = url;
        
    } catch (error) {
        showError(error.message);
    } finally {
        qrGenerateText.hidden = false;
        qrGenerateLoading.hidden = true;
        qrGenerateBtn.disabled = false;
    }
}

// Handle copy to clipboard
async function handleCopy() {
    const url = shortUrlInput.value;
    
    try {
        await navigator.clipboard.writeText(url);
        
        // Show copied state
        copyBtn.classList.add('copied');
        copyBtn.textContent = '✓';
        
        setTimeout(() => {
            copyBtn.classList.remove('copied');
            copyBtn.textContent = '📋';
        }, 2000);
        
    } catch (error) {
        // Fallback for older browsers
        shortUrlInput.select();
        document.execCommand('copy');
        
        copyBtn.classList.add('copied');
        copyBtn.textContent = '✓';
        
        setTimeout(() => {
            copyBtn.classList.remove('copied');
            copyBtn.textContent = '📋';
        }, 2000);
    }
}

// Show QR section (after shortening)
async function showQrSection() {
    if (!currentCode) return;
    
    qrSection.hidden = false;
    statsSection.hidden = true;
    
    // Show original URL
    qrOriginalUrl.textContent = currentOriginalUrl;
    
    // Generate QR code via API
    try {
        const response = await fetch(`${API_BASE}/api/qr/${currentCode}`);
        if (response.ok) {
            const data = await response.json();
            qrImage.src = `data:image/png;base64,${data.qr_code}`;
        }
    } catch (error) {
        console.error('Error loading QR code:', error);
    }
}

// Show stats section
async function showStatsSection() {
    if (!currentCode) return;
    
    statsSection.hidden = false;
    qrSection.hidden = true;
    
    try {
        const response = await fetch(`${API_BASE}/api/stats/${currentCode}`);
        if (!response.ok) throw new Error('Error al cargar estadísticas');
        
        const data = await response.json();
        
        // Update stats
        totalClicks.textContent = data.total_clicks;
        createdDate.textContent = new Date(data.created_at).toLocaleDateString('es-ES');
        
        // Render recent clicks
        clicksList.innerHTML = '';
        if (data.recent_clicks.length === 0) {
            clicksList.innerHTML = '<p style="color: var(--text-muted); text-align: center;">Aún no hay clics</p>';
        } else {
            data.recent_clicks.forEach(click => {
                const clickEl = document.createElement('div');
                clickEl.className = 'click-item';
                clickEl.innerHTML = `
                    <span class="click-ip">${click.ip_address || 'Desconocido'}</span>
                    <span class="click-time">${new Date(click.fecha_click).toLocaleString('es-ES')}</span>
                `;
                clicksList.appendChild(clickEl);
            });
        }
        
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Handle QR download (after shortening)
function handleDownloadQr() {
    if (!qrImage.src) return;
    
    const link = document.createElement('a');
    link.download = `davelink-${currentCode}-qr.png`;
    link.href = qrImage.src;
    link.click();
}

// Handle QR share
async function handleShareQr() {
    const shortUrl = shortUrlInput.value;
    
    if (navigator.share) {
        try {
            await navigator.share({
                title: 'daveLinK - Enlace acortado',
                text: 'Mira este enlace acortado:',
                url: shortUrl,
            });
        } catch (error) {
            console.error('Error sharing:', error);
        }
    } else {
        // Fallback: copy to clipboard
        await navigator.clipboard.writeText(shortUrl);
        shareQrBtn.textContent = '✓ Copiado';
        setTimeout(() => {
            shareQrBtn.textContent = '📤 Compartir';
        }, 2000);
    }
}

// Handle QR download (standalone generator)
function handleDownloadQrResult() {
    if (!qrResultImage.src) return;
    
    const code = qrResultImage.dataset.code || 'custom';
    const link = document.createElement('a');
    link.download = `davelink-qr-${code}.png`;
    link.href = qrResultImage.src;
    link.click();
}

// Handle copy QR result URL
async function handleCopyQrResult() {
    const url = qrResultImage.dataset.originalUrl || qrResultUrl.textContent;
    
    try {
        await navigator.clipboard.writeText(url);
        copyQrResultBtn.textContent = '✓ Copiado';
        setTimeout(() => {
            copyQrResultBtn.textContent = '📋 Copiar enlace';
        }, 2000);
    } catch (error) {
        console.error('Error copying:', error);
    }
}

// Helper functions
function setLoading(loading) {
    submitBtn.disabled = loading;
    btnText.hidden = loading;
    btnLoading.hidden = !loading;
}

function showError(message) {
    // Create or show error message
    let errorEl = document.querySelector('.error-message');
    if (!errorEl) {
        errorEl = document.createElement('p');
        errorEl.className = 'error-message';
        form.appendChild(errorEl);
    }
    errorEl.textContent = message;
    errorEl.classList.add('show');
    urlInput.classList.add('error');
}

function hideError() {
    const errorEl = document.querySelector('.error-message');
    if (errorEl) {
        errorEl.classList.remove('show');
    }
    urlInput.classList.remove('error');
}

// Auto-hide error on input
urlInput.addEventListener('input', hideError);
qrUrlInput.addEventListener('input', () => {
    const errorEl = document.querySelector('.error-message');
    if (errorEl) errorEl.classList.remove('show');
});

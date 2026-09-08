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
const downloadQrPngBtn = document.getElementById('download-qr-png');
const downloadQrSvgBtn = document.getElementById('download-qr-svg');
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
const downloadQrResultPngBtn = document.getElementById('download-qr-result-png');
const downloadQrResultSvgBtn = document.getElementById('download-qr-result-svg');
const copyQrResultBtn = document.getElementById('copy-qr-result');

// State
let currentCode = null;
let currentOriginalUrl = null;

// API Base URL
const API_BASE = '';

// ── Per-panel QR state (Slice 5) ────────────────────────────────────────────
// Each QR panel owns its config via makeQrPanel(). There is intentionally NO
// shared qrConfig singleton: mutating one panel must never re-render the other.

const QR_DEFAULTS = Object.freeze({
    fill_color: '#6366f1',
    back_color: '#ffffff',
    dot_style: 'square',
    size: 400,
    border: 4,
    error_correction: 'H',
    logo: '',
    format: 'png',
});

const QR_ERROR_MESSAGES = {
    insufficient_contrast: 'Low contrast: main and background colors need at least 3:1 contrast.',
    invalid_color: 'Invalid color value — use hex colors like #6366f1.',
    data_too_long: 'URL too long for a QR code at these settings — try a lower error-correction level.',
    invalid_url: 'That URL looks invalid — it must start with http:// or https://.',
};

function makeQrPanel(panelKey, imgEl) {
    const root = document.querySelector(`.qr-customization[data-qr-panel="${panelKey}"]`);
    const panel = {
        key: panelKey,
        root,
        imgEl,
        config: { ...QR_DEFAULTS },
        code: null, // link panel: short code for GET /api/qr/{code}.png|.svg
        url: null,  // raw panel: arbitrary URL for POST /api/qr/raw
        timer: null,
        warningEl: root ? root.querySelector('[data-qr-warning]') : null,
    };

    if (root) {
        const onInput = (event) => {
            const el = event.target;
            if (!el || !el.name) return;
            handlePanelInput(panel, el);
        };
        root.addEventListener('input', onInput);
        root.addEventListener('change', onInput);
        syncPngOnlyControls(panel);
    }
    return panel;
}

// Read a control element into the panel config. Returns true when the panel
// needs a re-render (config or format changed).
function handlePanelInput(panel, el) {
    clearPanelError(panel);
    const name = el.name;
    if (name === 'format') {
        panel.config.format = el.value === 'svg' ? 'svg' : 'png';
        syncPngOnlyControls(panel);
        schedulePanelRender(panel);
        return;
    }
    if (name === 'size' || name === 'size_value') {
        const value = clampSize(parseInt(el.value, 10));
        if (Number.isNaN(value)) return;
        panel.config.size = value;
        mirrorSizeInputs(panel, el, value);
        schedulePanelRender(panel);
        return;
    }
    if (name === 'border') {
        const value = Math.min(16, Math.max(0, parseInt(el.value, 10) || 0));
        panel.config.border = value;
        if (el.value !== String(value)) el.value = String(value);
        schedulePanelRender(panel);
        return;
    }
    if (!(name in panel.config)) return;
    panel.config[name] = el.value;
    schedulePanelRender(panel);
}

function clampSize(value) {
    if (Number.isNaN(value)) return NaN;
    return Math.min(2048, Math.max(64, value));
}

function mirrorSizeInputs(panel, sourceEl, value) {
    if (!panel.root) return;
    panel.root.querySelectorAll('[name="size"], [name="size_value"]').forEach((input) => {
        if (input !== sourceEl && input.value !== String(value)) input.value = String(value);
    });
}

// SVG is square-modules-only: logo presets and dot styles are PNG-only, so
// they are disabled (with tooltip from the title attribute) in SVG mode.
function syncPngOnlyControls(panel) {
    if (!panel.root) return;
    const isSvg = panel.config.format === 'svg';
    panel.root.querySelectorAll('[data-png-only]').forEach((el) => {
        el.disabled = isSvg;
    });
    panel.root.querySelectorAll('[data-png-only-wrap]').forEach((el) => {
        el.classList.toggle('is-disabled', isSvg);
    });
}

// Debounced re-render (300ms) — one timer per panel.
function schedulePanelRender(panel) {
    clearTimeout(panel.timer);
    panel.timer = setTimeout(() => renderPanel(panel), 300);
}

function panelHasSource(panel) {
    return Boolean(panel.code || panel.url);
}

async function renderPanel(panel) {
    if (!panelHasSource(panel)) return;
    clearPanelError(panel);
    try {
        if (panel.code) {
            await renderLinkPanel(panel);
        } else {
            await renderRawPanel(panel);
        }
    } catch (error) {
        console.error('QR render error:', error);
        showPanelError(panel, error.message || 'Failed to render QR code.', null, error.detail || '');
    }
}

// Post-shorten panel: binary GET /api/qr/{code}.png|.svg via fetch so HTTP
// errors (422 contrast) and the capacity_warning metadata stay visible.
// A JSON validation pass reads the warning; the bytes become an object URL.
async function renderLinkPanel(panel) {
    const query = buildQrQuery(panel.config, panel.config.format);
    const ext = panel.config.format === 'svg' ? 'svg' : 'png';
    const res = await fetch(`${API_BASE}/api/qr/${panel.code}.${ext}?${query}`);
    if (!res.ok) {
        throw await qrErrorFromResponse(res);
    }
    const blob = await res.blob();
    setPanelImage(panel, URL.createObjectURL(blob));
    // Metadata (capacity_warning) rides on the legacy JSON endpoint.
    try {
        const meta = await fetch(`${API_BASE}/api/qr/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: panel.code, config: panelConfigForBackend(panel) }),
        });
        if (meta.ok) {
            showCapacityWarning(panel, (await meta.json()).capacity_warning);
            return;
        }
    } catch {
        // Metadata is best-effort — the image already rendered.
    }
    showCapacityWarning(panel, null);
}

// Standalone panel: POST /api/qr/raw — encodes the arbitrary URL directly
// and NEVER writes a Link row. Response carries image + warning metadata.
async function renderRawPanel(panel) {
    const res = await fetch(`${API_BASE}/api/qr/raw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: panel.url, config: panelConfigForBackend(panel) }),
    });
    if (!res.ok) {
        throw await qrErrorFromResponse(res);
    }
    const data = await res.json();
    const mime = data.format === 'svg' ? 'image/svg+xml' : 'image/png';
    setPanelImage(panel, `data:${mime};base64,${data.qr_code}`);
    showCapacityWarning(panel, data.capacity_warning);
}

async function qrErrorFromResponse(res) {
    const data = await res.json().catch(() => ({}));
    const detail = typeof data.detail === 'string' ? data.detail : '';
    const message = QR_ERROR_MESSAGES[detail] || detail || `Request failed (${res.status})`;
    const error = new Error(message);
    error.detail = detail;
    return error;
}

function setPanelImage(panel, src) {
    if (panel.imgEl) {
        if (panel.imgEl.src && panel.imgEl.src.startsWith('blob:')) {
            URL.revokeObjectURL(panel.imgEl.src);
        }
        panel.imgEl.src = src;
    }
}

function buildQrQuery(config, format) {
    const params = new URLSearchParams({
        fill_color: config.fill_color,
        back_color: config.back_color,
        size: String(config.size),
        border: String(config.border),
        error_correction: config.error_correction,
    });
    if (format !== 'svg') {
        params.set('dot_style', config.dot_style);
        if (config.logo) params.set('logo', config.logo);
    }
    return params.toString();
}

// Backend QRConfig shape (format included; empty logo → null = no logo).
function panelConfigForBackend(panel) {
    const { format, ...rest } = panel.config;
    return { ...rest, logo: panel.config.logo || null, format: panel.config.format };
}

function friendlyWarning(warning) {
    if (!warning) return null;
    if (warning === 'logo_not_supported_for_long_urls') {
        return '⚠️ URL too long for a logo at High correction — degraded automatically.';
    }
    return `⚠️ ${warning}`;
}

function showCapacityWarning(panel, warning) {
    if (!panel.warningEl) return;
    const text = friendlyWarning(warning);
    panel.warningEl.hidden = !text;
    panel.warningEl.textContent = text || '';
}

// Inline panel error (rendered in-page, never as a modal popup). Contrast
// failures additionally highlight the offending color pickers.
function showPanelError(panel, message, highlightNames = null, detail = '') {
    if (!panel.root) return;
    let errEl = panel.root.querySelector('.qr-error');
    if (!errEl) {
        errEl = document.createElement('p');
        errEl.className = 'qr-error';
        errEl.setAttribute('role', 'alert');
        panel.root.appendChild(errEl);
    }
    errEl.textContent = message;
    const highlight = highlightNames
        || (detail === 'insufficient_contrast' ? ['fill_color', 'back_color'] : []);
    highlight.forEach((name) => {
        const input = panel.root.querySelector(`[name="${name}"]`);
        if (input) input.classList.add('invalid');
    });
}

function clearPanelError(panel) {
    if (!panel.root) return;
    panel.root.querySelectorAll('.qr-error').forEach((el) => el.remove());
    panel.root.querySelectorAll('.invalid').forEach((el) => el.classList.remove('invalid'));
}

const sectionPanel = makeQrPanel('section', qrImage);
const resultPanel = makeQrPanel('result', qrResultImage);

// Event Listeners
form.addEventListener('submit', handleSubmit);
copyBtn.addEventListener('click', handleCopy);
qrBtn.addEventListener('click', showQrSection);
statsBtn.addEventListener('click', showStatsSection);
closeQrBtn.addEventListener('click', () => qrSection.hidden = true);
closeStatsBtn.addEventListener('click', () => statsSection.hidden = true);
downloadQrPngBtn.addEventListener('click', () => handleDownloadLinkQr('png'));
downloadQrSvgBtn.addEventListener('click', () => handleDownloadLinkQr('svg'));
shareQrBtn.addEventListener('click', handleShareQr);

// QR Generator event listeners
qrForm.addEventListener('submit', handleQrGenerate);
closeQrResultBtn.addEventListener('click', () => qrResult.hidden = true);
downloadQrResultPngBtn.addEventListener('click', () => handleDownloadRawQr('png'));
downloadQrResultSvgBtn.addEventListener('click', () => handleDownloadRawQr('svg'));
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

// Handle QR code generation (standalone) — POST /api/qr/raw only.
// No Link row is created: the arbitrary URL is encoded directly.
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
        resultPanel.url = url;
        resultPanel.code = null;
        await renderPanel(resultPanel);

        // Show QR result
        qrResultUrl.textContent = url;
        qrResult.hidden = false;
    } catch (error) {
        // renderPanel already surfaced the inline error; keep the panel
        // visible so the user can see it.
        qrResult.hidden = false;
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

// Show QR section (after shortening) — binary endpoint, own panel state.
async function showQrSection() {
    if (!currentCode) return;

    qrSection.hidden = false;
    statsSection.hidden = true;

    // Show original URL
    qrOriginalUrl.textContent = currentOriginalUrl;

    // Point the post-shorten panel at this code and render with its config.
    sectionPanel.code = currentCode;
    sectionPanel.url = null;
    await renderPanel(sectionPanel);
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

// Download the post-shorten QR in the requested format, straight from the
// binary endpoint (current panel config encoded as query params).
function handleDownloadLinkQr(format) {
    if (!sectionPanel.code) return;

    const ext = format === 'svg' ? 'svg' : 'png';
    const query = buildQrQuery(sectionPanel.config, ext);
    const link = document.createElement('a');
    link.download = `davelink-${sectionPanel.code}-qr.${ext}`;
    link.href = `${API_BASE}/api/qr/${sectionPanel.code}.${ext}?${query}`;
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

// Download the standalone QR in the requested format via POST /api/qr/raw
// (no DB write). Falls back to the rendered image when nothing was generated.
async function handleDownloadRawQr(format) {
    const ext = format === 'svg' ? 'svg' : 'png';
    if (!resultPanel.url) return;

    try {
        const res = await fetch(`${API_BASE}/api/qr/raw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: resultPanel.url,
                config: { ...panelConfigForBackend(resultPanel), format: ext },
            }),
        });
        if (!res.ok) throw await qrErrorFromResponse(res);
        const data = await res.json();
        const bytes = Uint8Array.from(atob(data.qr_code), (c) => c.charCodeAt(0));
        const blob = new Blob([bytes], {
            type: ext === 'svg' ? 'image/svg+xml' : 'image/png',
        });
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.download = `davelink-qr-custom.${ext}`;
        link.href = objectUrl;
        link.click();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 5000);
    } catch (error) {
        console.error('QR download error:', error);
        showPanelError(resultPanel, error.message || 'Failed to download QR code.');
    }
}

// Handle copy QR result URL
async function handleCopyQrResult() {
    const url = resultPanel.url || qrResultUrl.textContent;
    
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

// ── Cache Status Indicator ────────────────────────────────────────────────

async function updateCacheStatus() {
    const dot = document.getElementById('cache-dot');
    const text = document.getElementById('cache-text');
    if (!dot || !text) return;

    try {
        const res = await fetch(`${API_BASE}/api/cache/status`);
        if (!res.ok) throw new Error('Sin respuesta');
        const data = await res.json();
        dot.className = 'cache-dot ' + (data.connected ? 'connected' : 'disconnected');
        text.textContent = data.message;
    } catch {
        dot.className = 'cache-dot disconnected';
        text.textContent = 'Cache: no disponible';
    }
}

// Check cache status on load and every 30s
updateCacheStatus();
setInterval(updateCacheStatus, 30000);

/* =====================================================================
   anomalies.js  –  Anomaly feed with filters and pagination
   ===================================================================== */

const PAGE_SIZE = 40;
let filteredAnomalies = [];
let displayedCount = 0;

const TYPE_META = {
    cost_outlier: { icon: '💰', color: '#f59e0b' },
    potential_duplicate: { icon: '📋', color: '#f04444' },
    duplicate_work: { icon: '📋', color: '#f04444' },
    contractor_concentration: { icon: '🏢', color: '#a78bfa' },
    payment_speed: { icon: '⚡', color: '#22c55e' },
    deduction_ratio: { icon: '📉', color: '#ec4899' },
    benford_violation: { icon: '🔢', color: '#06b6d4' },
    split_order: { icon: '✂️', color: '#f97316' },
    repeat_contractor: { icon: '🔄', color: '#84cc16' },
    repeat_work: { icon: '🔁', color: '#fb923c' },
    bid_anomaly: { icon: '📊', color: '#e879f9' },
};

function initAnomalies() {
    const anomalies = DATA.anomalies || [];
    filteredAnomalies = [...anomalies];
    renderAnomalyStats(anomalies);
    renderAnomalyFeed();
    wireAnomalyFilters();
}

/* ── stats chips ───────────────────────────────────────── */
function renderAnomalyStats(all) {
    const el = document.getElementById('anomaly-stats');
    if (!el) return;

    const counts = {};
    all.forEach(a => { const t = a.type || 'unknown'; counts[t] = (counts[t] || 0) + 1; });

    el.innerHTML = Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .map(([t, n]) => {
            const m = TYPE_META[t] || { icon: '❓', color: '#5f6680' };
            return `<div class="anomaly-stat-chip">
                <span class="anomaly-stat-dot" style="background:${m.color}"></span>
                <span>${t.replace(/_/g, ' ')}</span>
                <span class="anomaly-stat-count">${n}</span>
            </div>`;
        }).join('');
}

/* ── filters ───────────────────────────────────────────── */
function wireAnomalyFilters() {
    const typeFilter = document.getElementById('filter-type');
    const sevFilter = document.getElementById('filter-severity');
    const searchFilter = document.getElementById('filter-search');

    const handler = () => applyFilters();
    if (typeFilter) typeFilter.addEventListener('change', handler);
    if (sevFilter) sevFilter.addEventListener('change', handler);
    if (searchFilter) searchFilter.addEventListener('input', handler);
}

function applyFilters() {
    const type = (document.getElementById('filter-type') || {}).value || 'all';
    const sev = (document.getElementById('filter-severity') || {}).value || 'all';
    const q = ((document.getElementById('filter-search') || {}).value || '').trim().toLowerCase();

    const all = DATA.anomalies || [];
    filteredAnomalies = all.filter(a => {
        if (type !== 'all' && a.type !== type) return false;
        if (sev !== 'all' && a.severity !== sev) return false;
        if (q && !(a.description || '').toLowerCase().includes(q)
            && !(a.ward_name || '').toLowerCase().includes(q)
            && !String(a.ward_number || '').includes(q)) return false;
        return true;
    });

    renderAnomalyFeed();
}

/* ── feed rendering ────────────────────────────────────── */
function renderAnomalyFeed() {
    const list = document.getElementById('anomaly-list');
    const countEl = document.getElementById('anomaly-showing');
    const moreBtn = document.getElementById('load-more-btn');
    if (!list) return;

    displayedCount = Math.min(PAGE_SIZE, filteredAnomalies.length);
    list.innerHTML = filteredAnomalies.slice(0, displayedCount).map(renderAnomalyCard).join('');

    if (countEl) countEl.textContent = `Showing ${displayedCount} of ${filteredAnomalies.length}`;
    if (moreBtn) moreBtn.classList.toggle('hidden', displayedCount >= filteredAnomalies.length);
}

function loadMore() {
    const list = document.getElementById('anomaly-list');
    const countEl = document.getElementById('anomaly-showing');
    const moreBtn = document.getElementById('load-more-btn');
    if (!list) return;

    const nextBatch = filteredAnomalies.slice(displayedCount, displayedCount + PAGE_SIZE);
    list.insertAdjacentHTML('beforeend', nextBatch.map(renderAnomalyCard).join(''));
    displayedCount += nextBatch.length;

    if (countEl) countEl.textContent = `Showing ${displayedCount} of ${filteredAnomalies.length}`;
    if (moreBtn) moreBtn.classList.toggle('hidden', displayedCount >= filteredAnomalies.length);
}

function renderAnomalyCard(a) {
    const sev = a.severity || 'medium';
    const type = a.type || 'unknown';
    const meta = TYPE_META[type] || { icon: '❓', color: '#5f6680' };

    return `
    <div class="anomaly-card">
        <div class="anomaly-severity severity-${sev}"></div>
        <div class="anomaly-body">
            <div class="anomaly-top">
                <span class="anomaly-type-label" style="color:${meta.color}">${meta.icon} ${type.replace(/_/g, ' ')}</span>
                <span class="anomaly-badge badge-${sev}">${sev}</span>
            </div>
            <div class="anomaly-desc">${esc(a.description || '')}</div>
            <div class="anomaly-meta">
                ${a.ward_name ? `<span class="anomaly-meta-tag">📍 ${esc(a.ward_name)}</span>` : ''}
                ${a.ward_number ? `<span class="anomaly-meta-tag">Ward ${a.ward_number}</span>` : ''}
                ${a.category ? `<span class="anomaly-meta-tag">${esc(a.category)}</span>` : ''}
                ${a.score ? `<span class="anomaly-meta-tag">Score: ${Number(a.score).toFixed(2)}</span>` : ''}
            </div>
        </div>
    </div>`;
}

/* ── overview preview (top anomalies) ──────────────────── */
function renderOverviewAnomalies() {
    const el = document.getElementById('overview-anomalies');
    if (!el) return;
    const top = (DATA.anomalies || []).filter(a => a.severity === 'critical' || a.severity === 'high').slice(0, 5);
    if (!top.length) {
        el.innerHTML = '<div style="padding:1rem;color:var(--text-muted);text-align:center;">No critical anomalies found</div>';
        return;
    }
    el.innerHTML = top.map(renderAnomalyCard).join('');
}

// Called from app.js boot
const _origBoot = typeof renderOverview === 'function' ? renderOverview : null;
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(renderOverviewAnomalies, 500);
});

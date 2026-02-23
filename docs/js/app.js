/* =====================================================================
   app.js  –  Orchestrator: loads data, renders tabs, wires navigation
   ===================================================================== */

const DATA = {};
const BASE = (() => {
    const s = document.querySelector('script[src*="app.js"]');
    if (!s) return 'data/';
    return new URL('data/', new URL(s.src, location.href).href.replace(/js\/app\.js.*/, '')).pathname;
})();

/* ── helpers ────────────────────────────────────────────── */
function fmt(n) {
    if (n == null) return '—';
    if (typeof n === 'string') n = parseFloat(n);
    if (isNaN(n)) return '—';
    if (n >= 1e7) return (n / 1e7).toFixed(2) + ' Cr';
    if (n >= 1e5) return (n / 1e5).toFixed(1) + ' L';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toLocaleString('en-IN');
}
function fmtCr(lakhs) { return (lakhs / 100).toFixed(1) + ' Cr'; }
function fmtL(lakhs) { return Number(lakhs).toFixed(1) + ' L'; }
function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

/* ── data loading ──────────────────────────────────────── */
async function loadJSON(file) {
    const r = await fetch(BASE + file);
    if (!r.ok) throw new Error(`${file}: ${r.status}`);
    return r.json();
}

async function boot() {
    document.getElementById('loading').style.display = 'flex';
    try {
        const files = ['meta.json','summary.json','wards.json','anomalies.json',
                        'contractors.json','timeseries.json','zones.json','insights.json'];
        const results = await Promise.allSettled(files.map(f => loadJSON(f)));
        files.forEach((f, i) => {
            const key = f.replace('.json','');
            DATA[key] = results[i].status === 'fulfilled' ? results[i].value : (key === 'zones' || key === 'insights' ? [] : {});
        });
        renderNav();
        renderOverview();
        if (typeof initMap === 'function') initMap();
        if (typeof initCharts === 'function') initCharts();
        if (typeof initAnomalies === 'function') initAnomalies();
    } catch (e) {
        console.error('Boot error:', e);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

/* ── nav ───────────────────────────────────────────────── */
function renderNav() {
    const m = DATA.meta || {};
    const el = document.getElementById('nav-updated');
    if (el) el.textContent = m.generated ? fmtDate(m.generated) : '';
}

function switchTab(name) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
    const tab = document.getElementById('tab-' + name);
    if (tab) tab.classList.add('active');
    document.querySelectorAll(`.nav-tab[data-tab="${name}"]`).forEach(b => b.classList.add('active'));
    // Trigger map resize after tab becomes visible
    if (name === 'map' && typeof refreshMap === 'function') {
        setTimeout(refreshMap, 100);
    }
}

/* ── overview ──────────────────────────────────────────── */
function renderOverview() {
    const m = DATA.meta || {};
    const s = DATA.summary || {};

    // Hero stats
    setText('stat-orders', fmt(m.total_records));
    setText('stat-spend', fmtCr(s.total_gross_lakhs || 0));
    setText('stat-wards', m.total_wards || '—');
    setText('stat-anomalies', fmt(m.total_anomalies));
    setText('stat-critical', fmt((m.critical_anomalies || 0) + (m.high_anomalies || 0)));

    // Insights
    renderInsights();

    // Zone table
    renderZoneTable();
}

function renderInsights() {
    const el = document.getElementById('insights-grid');
    if (!el) return;
    const items = Array.isArray(DATA.insights) ? DATA.insights : [];
    if (!items.length) { el.innerHTML = ''; return; }
    const icons = {
        largest_order: '💰', top_contractor: '🏗️', most_flagged_ward: '🚩',
        highest_spend_ward: '📊', largest_category: '🏷️', duplicate_value: '⚠️'
    };
    el.innerHTML = items.map(i => `
        <div class="insight-card">
            <div class="insight-icon">${icons[i.type] || '📋'}</div>
            <div class="insight-body">
                <div class="insight-title">${esc(i.label)}</div>
                <div class="insight-value">${esc(i.value)}</div>
                <div class="insight-detail" title="${esc(i.detail)}">${esc(i.detail)}</div>
            </div>
        </div>`).join('');
}

function renderZoneTable() {
    const el = document.getElementById('zone-tbody');
    if (!el) return;
    const zones = Array.isArray(DATA.zones) ? DATA.zones : [];
    if (!zones.length) { el.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No zone data</td></tr>'; return; }
    const maxSpend = Math.max(...zones.map(z => z.total_gross_lakhs || 0), 1);
    el.innerHTML = zones.map(z => `
        <tr>
            <td>${esc(z.zone)}</td>
            <td class="mono">${z.ward_count || 0}</td>
            <td>
                <div style="display:flex;align-items:center;gap:0.5rem;">
                    <div class="zone-bar" style="width:${((z.total_gross_lakhs||0)/maxSpend*100).toFixed(0)}%"></div>
                    <span class="mono">${fmtCr(z.total_gross_lakhs||0)}</span>
                </div>
            </td>
            <td class="mono">${fmt(z.total_orders)}</td>
            <td class="mono">${z.total_anomalies||0}</td>
        </tr>`).join('');
}

/* ── shared utilities ──────────────────────────────────── */
function setText(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }
function esc(s) { if (!s) return ''; const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

/* ── start ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', boot);

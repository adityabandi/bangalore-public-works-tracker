/* =====================================================================
   app.js — Core orchestrator: data loading, indexes, nav, shared utils
   ===================================================================== */

const DATA = {};
const BASE = (() => {
    const s = document.querySelector('script[src*="app.js"]');
    if (!s) return 'data/';
    return new URL('data/', new URL(s.src, location.href).href.replace(/js\/app\.js.*/, '')).pathname;
})();

/* ── Type metadata (shared across all views) ──────────── */
const TYPE_META = {
    cost_outlier:              { icon: '💰', color: '#f59e0b', label: 'Cost Outlier' },
    contractor_concentration:  { icon: '🏢', color: '#a78bfa', label: 'Contractor Concentration' },
    duplicate_work:            { icon: '📋', color: '#ef4444', label: 'Duplicate Work' },
    payment_speed:             { icon: '⚡', color: '#22c55e', label: 'Payment Speed' },
    deduction_ratio:           { icon: '📉', color: '#ec4899', label: 'Deduction Ratio' },
    benford_violation:         { icon: '🔢', color: '#06b6d4', label: 'Benford Violation' },
    split_order:               { icon: '✂️', color: '#f97316', label: 'Split Order' },
    repeat_contractor:         { icon: '🔄', color: '#84cc16', label: 'Repeat Contractor' },
    repeat_work:               { icon: '🔁', color: '#fb923c', label: 'Repeat Work' },
    bid_anomaly:               { icon: '📊', color: '#e879f9', label: 'Bid Anomaly' },
};

const CAT_COLORS = {
    roads: '#f59e0b', drainage: '#06b6d4', buildings: '#a78bfa', lighting: '#facc15',
    water: '#3b82f6', swm: '#22c55e', surveillance: '#ec4899', other: '#6b7280',
};

const CHART_COLORS = ['#5b8def','#f59e0b','#22c55e','#ef4444','#a78bfa','#ec4899','#06b6d4','#84cc16','#f97316','#64748b'];

/* ── Formatting helpers ────────────────────────────────── */
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
function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function setText(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }
function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : (s || ''); }

/* ── Data loading ──────────────────────────────────────── */
async function loadJSON(file) {
    const r = await fetch(BASE + file);
    if (!r.ok) throw new Error(`${file}: ${r.status}`);
    return r.json();
}

async function boot() {
    document.getElementById('loading').style.display = 'flex';
    try {
        const files = ['meta.json','summary.json','wards.json','anomalies.json',
            'contractors.json','timeseries.json','zones.json','insights.json',
            'repeat_works.json','bids.json','tenders.json'];
        const results = await Promise.allSettled(files.map(f => loadJSON(f)));
        files.forEach((f, i) => {
            const key = f.replace('.json', '');
            DATA[key] = results[i].status === 'fulfilled' ? results[i].value
                : (key === 'zones' || key === 'insights' ? [] : {});
        });

        buildIndex();
        renderNav();

        if (typeof initDashboard === 'function') initDashboard();
        if (typeof initMap === 'function') initMap();
        if (typeof initInvestigate === 'function') initInvestigate();
        if (typeof initCharts === 'function') initCharts();
    } catch (e) {
        console.error('Boot error:', e);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

/* ── Cross-reference indexes ───────────────────────────── */
function buildIndex() {
    DATA._contractorIndex = {};
    DATA._wardIndex = {};
    DATA._typeIndex = {};

    // Seed contractor index from contractors.json
    (Array.isArray(DATA.contractors) ? DATA.contractors : []).forEach(c => {
        const name = (c.contractor || '').toUpperCase();
        if (!name) return;
        DATA._contractorIndex[name] = { ...c, anomalies: [], wardSet: new Set(c.top_wards || []) };
    });

    // Seed ward index from wards.json
    const wards = DATA.wards || {};
    Object.entries(wards).forEach(([num, w]) => {
        DATA._wardIndex[String(num)] = { ...w, ward_num: num, anomalies: [] };
    });

    // Seed type index
    Object.keys(TYPE_META).forEach(t => {
        DATA._typeIndex[t] = { anomalies: [], critical: 0, high: 0, medium: 0, low: 0, total: 0 };
    });

    // Iterate anomalies to cross-reference
    (Array.isArray(DATA.anomalies) ? DATA.anomalies : []).forEach(a => {
        const t = a.type || '';
        const ward = String(a.ward_number || '');
        const sev = a.severity || 'medium';

        // Type index
        if (DATA._typeIndex[t]) {
            DATA._typeIndex[t].anomalies.push(a);
            DATA._typeIndex[t][sev] = (DATA._typeIndex[t][sev] || 0) + 1;
            DATA._typeIndex[t].total++;
        }

        // Ward index
        if (ward && DATA._wardIndex[ward]) {
            DATA._wardIndex[ward].anomalies.push(a);
        }

        // Contractor index — try to extract from description
        const desc = (a.description || '').toUpperCase();
        for (const cName of Object.keys(DATA._contractorIndex)) {
            if (cName.length > 3 && desc.includes(cName)) {
                DATA._contractorIndex[cName].anomalies.push(a);
                if (ward) DATA._contractorIndex[cName].wardSet.add(ward);
                break; // one match is enough
            }
        }
    });
}

/* ── Navigation ────────────────────────────────────────── */
function renderNav() {
    const m = DATA.meta || {};
    const el = document.getElementById('nav-updated');
    if (el) el.textContent = m.generated_at ? fmtDate(m.generated_at) : '';

    const critical = (m.critical_anomalies || 0) + (m.high_anomalies || 0);
    const pulseText = document.getElementById('nav-pulse-text');
    if (pulseText) pulseText.textContent = `${critical} critical+high`;
}

function switchTab(name) {
    document.querySelectorAll('.tab-content').forEach(t => {
        t.classList.remove('active');
        t.style.display = 'none';
    });
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
    const tab = document.getElementById('tab-' + name);
    if (tab) { tab.classList.add('active'); tab.style.display = ''; }
    document.querySelectorAll(`.nav-tab[data-tab="${name}"]`).forEach(b => b.classList.add('active'));
    if (name === 'map' && typeof refreshMap === 'function') setTimeout(refreshMap, 100);
}

/* ── Shared anomaly card renderer ──────────────────────── */
function renderAnomalyCard(a) {
    const sev = a.severity || 'medium';
    const type = a.type || 'unknown';
    const meta = TYPE_META[type] || { icon: '❓', color: '#5a6178', label: type };

    return `
    <div class="anomaly-card">
        <div class="anomaly-severity severity-${sev}"></div>
        <div class="anomaly-body">
            <div class="anomaly-top">
                <span class="anomaly-type-label" style="color:${meta.color}">${meta.icon} ${meta.label}</span>
                <span class="anomaly-badge badge-${sev}">${sev}</span>
            </div>
            <div class="anomaly-desc">${esc(a.description || '')}</div>
            <div class="anomaly-meta">
                ${a.ward_name ? `<span class="anomaly-meta-tag" onclick="showWard('${esc(a.ward_number || '')}')">📍 ${esc(a.ward_name)}</span>` : ''}
                ${a.ward_number ? `<span class="anomaly-meta-tag" onclick="showWard('${esc(a.ward_number)}')">Ward ${esc(String(a.ward_number))}</span>` : ''}
                ${a.category ? `<span class="anomaly-meta-tag">${esc(a.category)}</span>` : ''}
                ${a.score ? `<span class="anomaly-meta-tag">Score: ${Number(a.score).toFixed(2)}</span>` : ''}
            </div>
        </div>
    </div>`;
}

/* Navigate to ward in investigate tab */
function showWard(wardNum) {
    if (!wardNum) return;
    switchTab('investigate');
    if (typeof showWardDossier === 'function') showWardDossier(wardNum);
}

/* Navigate to contractor in investigate tab */
function showContractor(name) {
    if (!name) return;
    switchTab('investigate');
    if (typeof showContractorDossier === 'function') showContractorDossier(name);
}

/* ── Start ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', boot);

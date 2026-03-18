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
    cost_outlier:              { icon: '💰', color: '#D97706', label: 'Cost Outlier' },
    contractor_concentration:  { icon: '🏢', color: '#7C3AED', label: 'Contractor Concentration' },
    duplicate_work:            { icon: '📋', color: '#DC2626', label: 'Duplicate Work' },
    payment_speed:             { icon: '⚡', color: '#059669', label: 'Payment Speed' },
    deduction_ratio:           { icon: '📉', color: '#DB2777', label: 'Deduction Ratio' },
    benford_violation:         { icon: '🔢', color: '#0891B2', label: 'Benford Violation' },
    split_order:               { icon: '✂️', color: '#EA580C', label: 'Split Order' },
    repeat_contractor:         { icon: '🔄', color: '#65A30D', label: 'Repeat Contractor' },
    repeat_work:               { icon: '🔁', color: '#E77E22', label: 'Repeat Work' },
    bid_anomaly:               { icon: '📊', color: '#A855F7', label: 'Bid Anomaly' },
};

const CAT_COLORS = {
    roads: '#D97706', drainage: '#0891B2', buildings: '#7C3AED', lighting: '#EAB308',
    water: '#2563EB', swm: '#059669', surveillance: '#DB2777', other: '#6B7280',
};

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
            'repeat_works.json','bids.json','tenders.json','stories.json'];
        const results = await Promise.allSettled(files.map(f => loadJSON(f)));
        files.forEach((f, i) => {
            const key = f.replace('.json', '');
            DATA[key] = results[i].status === 'fulfilled' ? results[i].value
                : (key === 'zones' || key === 'insights' ? [] : {});
        });

        buildIndex();
        renderNav();

        if (typeof initStories === 'function') initStories();
        if (typeof initMap === 'function') initMap();
        if (typeof initInvestigate === 'function') initInvestigate();
        if (typeof initCharts === 'function') initCharts();
        // Delay so investigation content is rendered before observer attaches
        setTimeout(() => initScrollSpy(), 100);
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

    (Array.isArray(DATA.contractors) ? DATA.contractors : []).forEach(c => {
        const name = (c.contractor || '').toUpperCase();
        if (!name) return;
        DATA._contractorIndex[name] = { ...c, anomalies: [], wardSet: new Set(c.top_wards || []) };
    });

    const wards = DATA.wards || {};
    Object.entries(wards).forEach(([num, w]) => {
        DATA._wardIndex[String(num)] = { ...w, ward_num: num, anomalies: [] };
    });

    Object.keys(TYPE_META).forEach(t => {
        DATA._typeIndex[t] = { anomalies: [], critical: 0, high: 0, medium: 0, low: 0, total: 0 };
    });

    (Array.isArray(DATA.anomalies) ? DATA.anomalies : []).forEach(a => {
        const t = a.type || '';
        const ward = String(a.ward_number || '');
        const sev = a.severity || 'medium';

        if (DATA._typeIndex[t]) {
            DATA._typeIndex[t].anomalies.push(a);
            DATA._typeIndex[t][sev] = (DATA._typeIndex[t][sev] || 0) + 1;
            DATA._typeIndex[t].total++;
        }

        if (ward && DATA._wardIndex[ward]) {
            DATA._wardIndex[ward].anomalies.push(a);
        }

        const desc = (a.description || '').toUpperCase();
        for (const cName of Object.keys(DATA._contractorIndex)) {
            if (cName.length > 3 && desc.includes(cName)) {
                DATA._contractorIndex[cName].anomalies.push(a);
                if (ward) DATA._contractorIndex[cName].wardSet.add(ward);
                break;
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
    if (pulseText) pulseText.textContent = `${critical.toLocaleString()} critical+high`;
}

function scrollToSection(id) {
    const el = document.getElementById(id);
    if (el) {
        const offset = document.getElementById('nav').offsetHeight + 16;
        const top = el.getBoundingClientRect().top + window.pageYOffset - offset;
        window.scrollTo({ top, behavior: 'smooth' });
    }
    // Update active tab
    document.querySelectorAll('.nav-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.section === id);
    });
    // If navigating to map, refresh it
    if (id === 'map-section' && typeof refreshMap === 'function') setTimeout(refreshMap, 300);
}

/* ── Scroll Spy ────────────────────────────────────────── */
function initScrollSpy() {
    const sections = ['findings', 'numbers', 'map-section', 'explore', 'methodology'];
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                document.querySelectorAll('.nav-tab').forEach(b => {
                    b.classList.toggle('active', b.dataset.section === entry.target.id);
                });
            }
        });
    }, { rootMargin: '-20% 0px -70% 0px' });

    sections.forEach(id => {
        const el = document.getElementById(id);
        if (el) observer.observe(el);
    });

    // Fade in investigations on scroll
    const invObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) entry.target.classList.add('visible');
        });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.1 });

    document.querySelectorAll('.investigation').forEach(el => invObserver.observe(el));
}

/* ── Explore tab switching ────────────────────────────── */
function switchExploreView(view) {
    document.getElementById('explore-investigate').style.display = view === 'investigate' ? '' : 'none';
    document.getElementById('explore-data').style.display = view === 'data' ? '' : 'none';
    document.querySelectorAll('.explore-tab').forEach(b => {
        b.classList.toggle('active', b.textContent.toLowerCase().includes(view === 'investigate' ? 'invest' : 'data'));
    });
    if (view === 'data' && typeof switchDataTab === 'function') switchDataTab('contractors');
}

/* Keep legacy switchTab for investigate.js compatibility */
function switchTab(name) {
    if (name === 'investigate') {
        scrollToSection('explore');
        switchExploreView('investigate');
    } else if (name === 'data') {
        scrollToSection('explore');
        switchExploreView('data');
    } else if (name === 'map') {
        scrollToSection('map-section');
    }
}

/* ── Shared anomaly card renderer ──────────────────────── */
function renderAnomalyCard(a) {
    const sev = a.severity || 'medium';
    const type = a.type || 'unknown';
    const meta = TYPE_META[type] || { icon: '❓', color: '#6B7280', label: type };

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

function showWard(wardNum) {
    if (!wardNum) return;
    scrollToSection('explore');
    switchExploreView('investigate');
    if (typeof showWardDossier === 'function') showWardDossier(wardNum);
}

function showContractor(name) {
    if (!name) return;
    scrollToSection('explore');
    switchExploreView('investigate');
    if (typeof showContractorDossier === 'function') showContractorDossier(name);
}

/* ── Start ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', boot);

/* =====================================================================
   investigate.js — Unified investigation + Data tab
   ===================================================================== */

const INV_PAGE = 50;
let invState = {
    entity: 'anomalies',
    sevFilter: new Set(['critical', 'high']),
    typeFilter: null,  // null = all
    catFilter: null,
    query: '',
    filtered: [],
    displayed: 0,
};

/* ── Data tab state ────────────────────────────────────── */
const DATA_PAGE = 100;
let dataState = {
    tab: 'contractors',
    query: '',
    filtered: [],
    displayed: 0,
    sortCol: null,
    sortAsc: false,
};

/* ============================================================
   INVESTIGATE TAB
   ============================================================ */

function initInvestigate() {
    renderTypeFilter();
    renderCatFilter();
    wireInvControls();
    applyInvFilters();

    // Data tab initial render
    switchDataTab('contractors');
}

/* ── Sidebar: type filter ──────────────────────────────── */
function renderTypeFilter() {
    const el = document.getElementById('inv-type-filter');
    if (!el) return;
    const types = Object.entries(DATA._typeIndex || {}).filter(([, v]) => v.total > 0).sort((a, b) => b[1].total - a[1].total);
    el.innerHTML = `<div class="inv-cat-item ${!invState.typeFilter ? 'active' : ''}" onclick="setTypeFilter(null)">
        <span class="inv-cat-dot" style="background:var(--accent)"></span> All Types
    </div>` + types.map(([t, d]) => {
        const m = TYPE_META[t] || { icon: '❓', color: '#5a6178' };
        return `<div class="inv-cat-item ${invState.typeFilter === t ? 'active' : ''}" onclick="setTypeFilter('${t}')">
            <span class="inv-cat-dot" style="background:${m.color}"></span> ${m.icon} ${(TYPE_META[t] || {}).label || t} <span style="color:var(--text-dim);margin-left:auto;font-size:0.68rem">${d.total}</span>
        </div>`;
    }).join('');
}

/* ── Sidebar: category filter ──────────────────────────── */
function renderCatFilter() {
    const el = document.getElementById('inv-cat-filter');
    if (!el) return;
    const cats = Object.keys(CAT_COLORS);
    el.innerHTML = `<div class="inv-cat-item ${!invState.catFilter ? 'active' : ''}" onclick="setCatFilter(null)">
        <span class="inv-cat-dot" style="background:var(--accent)"></span> All Categories
    </div>` + cats.map(c => `<div class="inv-cat-item ${invState.catFilter === c ? 'active' : ''}" onclick="setCatFilter('${c}')">
        <span class="inv-cat-dot" style="background:${CAT_COLORS[c]}"></span> ${c}
    </div>`).join('');
}

/* ── Controls wiring ───────────────────────────────────── */
function wireInvControls() {
    const search = document.getElementById('inv-search');
    if (search) search.addEventListener('input', () => { invState.query = search.value.trim().toLowerCase(); applyInvFilters(); });
}

function setEntity(e) {
    invState.entity = e;
    document.querySelectorAll('.inv-entity-btn').forEach(b => b.classList.toggle('active', b.dataset.entity === e));
    document.getElementById('inv-dossier').innerHTML = '';
    applyInvFilters();
}

function toggleSev(sev) {
    if (invState.sevFilter.has(sev)) invState.sevFilter.delete(sev); else invState.sevFilter.add(sev);
    document.querySelectorAll('.inv-sev-btn').forEach(b => b.classList.toggle('active', invState.sevFilter.has(b.dataset.sev)));
    applyInvFilters();
}

function setTypeFilter(type) {
    invState.typeFilter = type;
    renderTypeFilter();
    applyInvFilters();
}

function setCatFilter(cat) {
    invState.catFilter = cat;
    renderCatFilter();
    applyInvFilters();
}

/* ── Filtering ─────────────────────────────────────────── */
function applyInvFilters() {
    const all = Array.isArray(DATA.anomalies) ? DATA.anomalies : [];

    if (invState.entity === 'contractors') {
        renderContractorList();
        return;
    }

    if (invState.entity === 'wards') {
        renderWardList();
        return;
    }

    // Anomalies view
    invState.filtered = all.filter(a => {
        if (invState.sevFilter.size > 0 && !invState.sevFilter.has(a.severity)) return false;
        if (invState.typeFilter && a.type !== invState.typeFilter) return false;
        if (invState.catFilter && a.category !== invState.catFilter) return false;
        if (invState.query) {
            const q = invState.query;
            if (!(a.description || '').toLowerCase().includes(q) &&
                !(a.ward_name || '').toLowerCase().includes(q) &&
                !String(a.ward_number || '').includes(q)) return false;
        }
        return true;
    });

    invState.displayed = 0;
    renderInvResults();
}

/* ── Results rendering ─────────────────────────────────── */
function renderInvResults() {
    const list = document.getElementById('inv-results');
    const countEl = document.getElementById('inv-count');
    const moreBtn = document.getElementById('inv-load-more');
    if (!list) return;

    const batch = invState.filtered.slice(invState.displayed, invState.displayed + INV_PAGE);
    if (invState.displayed === 0) {
        list.innerHTML = batch.map(renderAnomalyCard).join('');
    } else {
        list.insertAdjacentHTML('beforeend', batch.map(renderAnomalyCard).join(''));
    }
    invState.displayed += batch.length;

    if (countEl) countEl.textContent = `Showing ${invState.displayed} of ${invState.filtered.length}`;
    if (moreBtn) moreBtn.classList.toggle('hidden', invState.displayed >= invState.filtered.length);
}

function invLoadMore() {
    renderInvResults();
}

/* ── Contractor list view ──────────────────────────────── */
function renderContractorList() {
    const list = document.getElementById('inv-results');
    const countEl = document.getElementById('inv-count');
    const moreBtn = document.getElementById('inv-load-more');
    if (!list) return;

    let contractors = Array.isArray(DATA.contractors) ? [...DATA.contractors] : [];
    if (invState.query) {
        const q = invState.query;
        contractors = contractors.filter(c => (c.contractor || '').toLowerCase().includes(q));
    }
    contractors.sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0));

    const batch = contractors.slice(0, INV_PAGE);
    invState.filtered = contractors;
    invState.displayed = batch.length;

    list.innerHTML = batch.map((c, i) => {
        const risk = c.risk_score || 0;
        const riskClass = risk >= 0.6 ? 'risk-crit' : risk >= 0.3 ? 'risk-high' : risk >= 0.1 ? 'risk-med' : 'risk-low';
        const totalFlags = (c.anomaly_count || 0) + (c.repeat_work_count || 0) + (c.bid_outlier_count || 0);
        return `<div class="anomaly-card" style="cursor:pointer" onclick="showContractorDossier('${esc(c.contractor)}')">
            <div class="anomaly-severity ${risk >= 0.6 ? 'severity-critical' : risk >= 0.3 ? 'severity-high' : 'severity-medium'}"></div>
            <div class="anomaly-body">
                <div class="anomaly-top">
                    <span style="font-weight:700;font-size:0.88rem;">${esc(truncate(c.contractor, 40))}</span>
                    <span class="risk-badge ${riskClass}">${risk.toFixed(2)} risk</span>
                </div>
                <div class="anomaly-meta" style="margin-top:0.25rem;">
                    <span class="anomaly-meta-tag">₹${fmtL(c.gross_lakhs || 0)}</span>
                    <span class="anomaly-meta-tag">${c.orders || 0} orders</span>
                    <span class="anomaly-meta-tag">${c.wards || 0} wards</span>
                    ${totalFlags > 0 ? `<span class="anomaly-meta-tag" style="color:var(--critical)">${totalFlags} flags</span>` : ''}
                </div>
            </div>
        </div>`;
    }).join('');

    if (countEl) countEl.textContent = `${contractors.length} contractors`;
    if (moreBtn) moreBtn.classList.add('hidden');
}

/* ── Ward list view ────────────────────────────────────── */
function renderWardList() {
    const list = document.getElementById('inv-results');
    const countEl = document.getElementById('inv-count');
    const moreBtn = document.getElementById('inv-load-more');
    if (!list) return;

    let wards = Object.entries(DATA._wardIndex || {}).map(([k, v]) => ({ num: k, ...v }));
    if (invState.query) {
        const q = invState.query;
        wards = wards.filter(w => (w.ward_name || '').toLowerCase().includes(q) || w.num.includes(q));
    }
    wards.sort((a, b) => (b.anomaly_count || 0) - (a.anomaly_count || 0));

    const batch = wards.slice(0, INV_PAGE);
    invState.filtered = wards;
    invState.displayed = batch.length;

    list.innerHTML = batch.map(w => {
        const ac = w.anomaly_count || 0;
        const sevClass = ac > 20 ? 'severity-critical' : ac > 10 ? 'severity-high' : 'severity-medium';
        return `<div class="anomaly-card" style="cursor:pointer" onclick="showWardDossier('${w.num}')">
            <div class="anomaly-severity ${sevClass}"></div>
            <div class="anomaly-body">
                <div class="anomaly-top">
                    <span style="font-weight:700;font-size:0.88rem;">Ward ${w.num} — ${esc(w.ward_name || '')}</span>
                    <span class="anomaly-badge ${ac > 20 ? 'badge-critical' : ac > 10 ? 'badge-high' : 'badge-medium'}">${ac} flags</span>
                </div>
                <div class="anomaly-meta" style="margin-top:0.25rem;">
                    <span class="anomaly-meta-tag">₹${fmtCr(w.total_gross_lakhs || 0)}</span>
                    <span class="anomaly-meta-tag">${w.total_orders || 0} orders</span>
                    <span class="anomaly-meta-tag">${esc(w.zone || '')} zone</span>
                </div>
            </div>
        </div>`;
    }).join('');

    if (countEl) countEl.textContent = `${wards.length} wards`;
    if (moreBtn) moreBtn.classList.add('hidden');
}

/* ── Contractor Dossier ────────────────────────────────── */
function showContractorDossier(name) {
    const el = document.getElementById('inv-dossier');
    if (!el) return;
    const key = (name || '').toUpperCase();
    const c = DATA._contractorIndex[key];
    if (!c) { el.innerHTML = ''; return; }

    const risk = c.risk_score || 0;
    const riskClass = risk >= 0.6 ? 'crit' : risk >= 0.3 ? 'high' : risk >= 0.1 ? 'med' : 'low';
    const dots = Array.from({ length: 5 }, (_, i) => {
        const level = risk >= (i + 1) * 0.2;
        return `<div class="risk-meter-dot ${level ? 'filled-' + riskClass : ''}"></div>`;
    }).join('');

    const anomalies = c.anomalies || [];
    const topAnomalies = anomalies.slice(0, 5);

    el.innerHTML = `
    <div class="dossier">
        <div class="dossier-header">
            <div>
                <div class="dossier-title">🏢 ${esc(name)}</div>
                <div class="dossier-subtitle">Contractor Dossier</div>
            </div>
            <div class="dossier-risk">
                <div class="risk-meter">${dots}</div>
                <span class="risk-label ${riskClass}">${risk >= 0.6 ? 'HIGH RISK' : risk >= 0.3 ? 'MEDIUM' : 'LOW'}</span>
            </div>
        </div>
        <div class="dossier-stats">
            <div class="dossier-stat"><div class="dossier-stat-value">₹${fmtL(c.gross_lakhs || 0)}</div><div class="dossier-stat-label">Total Spend</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value">${c.orders || 0}</div><div class="dossier-stat-label">Orders</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value">${c.wards || 0}</div><div class="dossier-stat-label">Wards</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value" style="color:var(--critical)">${c.anomaly_count || 0}</div><div class="dossier-stat-label">Anomaly Flags</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value" style="color:var(--high)">${c.repeat_work_count || 0}</div><div class="dossier-stat-label">Repeat Works</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value" style="color:var(--high)">${c.bid_outlier_count || 0}</div><div class="dossier-stat-label">Bid Outliers</div></div>
        </div>
        <div class="dossier-body">
            ${(c.top_categories || []).length ? `<div class="dossier-section">
                <h4>Top Categories</h4>
                <div>${(c.top_categories || []).map(cat => `<span class="anomaly-meta-tag" style="margin-right:0.4rem">${esc(cat)}</span>`).join('')}</div>
            </div>` : ''}
            ${topAnomalies.length ? `<div class="dossier-section">
                <h4>Related Anomalies <span class="count">${anomalies.length}</span></h4>
                <div class="anomaly-list">${topAnomalies.map(renderAnomalyCard).join('')}</div>
            </div>` : ''}
        </div>
    </div>`;

    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ── Ward Dossier ──────────────────────────────────────── */
function showWardDossier(wardNum) {
    const el = document.getElementById('inv-dossier');
    if (!el) return;
    const w = DATA._wardIndex[String(wardNum)];
    if (!w) { el.innerHTML = ''; return; }

    const anomalies = w.anomalies || [];
    const topAnomalies = anomalies.slice(0, 5);
    const ac = w.anomaly_count || 0;
    const riskClass = ac > 20 ? 'crit' : ac > 10 ? 'high' : ac > 5 ? 'med' : 'low';

    const cats = w.category_breakdown || {};
    const topCats = Object.entries(cats).sort((a, b) => b[1] - a[1]).slice(0, 6);
    const contractors = w.top_contractors || [];

    el.innerHTML = `
    <div class="dossier">
        <div class="dossier-header">
            <div>
                <div class="dossier-title">📍 Ward ${wardNum} — ${esc(w.ward_name || '')}</div>
                <div class="dossier-subtitle">${esc(w.zone || '')} Zone</div>
            </div>
            <div class="dossier-risk">
                <span class="risk-label ${riskClass}">${ac} ANOMALIES</span>
            </div>
        </div>
        <div class="dossier-stats">
            <div class="dossier-stat"><div class="dossier-stat-value">₹${fmtCr(w.total_gross_lakhs || 0)}</div><div class="dossier-stat-label">Total Spend</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value">${w.total_orders || 0}</div><div class="dossier-stat-label">Orders</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value" style="color:var(--critical)">${ac}</div><div class="dossier-stat-label">Anomalies</div></div>
            <div class="dossier-stat"><div class="dossier-stat-value">${(w.anomaly_score || 0).toFixed(2)}</div><div class="dossier-stat-label">Risk Score</div></div>
        </div>
        <div class="dossier-body">
            ${topCats.length ? `<div class="dossier-section">
                <h4>Category Breakdown</h4>
                <div>${topCats.map(([c, v]) => `<div style="display:flex;justify-content:space-between;padding:0.2rem 0;font-size:0.8rem;">
                    <span style="color:var(--text-secondary)">${esc(c)}</span>
                    <span style="font-family:var(--font-mono);font-weight:500">${v}</span>
                </div>`).join('')}</div>
            </div>` : ''}
            ${contractors.length ? `<div class="dossier-section">
                <h4>Top Contractors</h4>
                <div>${contractors.slice(0, 5).map(c => `<div style="display:flex;justify-content:space-between;padding:0.2rem 0;font-size:0.8rem;">
                    <span class="clickable" onclick="showContractorDossier('${esc(c.name)}')" style="color:var(--accent);cursor:pointer">${esc(truncate(c.name, 30))}</span>
                    <span style="font-family:var(--font-mono);font-weight:500">₹${fmtL(c.value_lakhs)}</span>
                </div>`).join('')}</div>
            </div>` : ''}
            ${topAnomalies.length ? `<div class="dossier-section">
                <h4>Anomalies <span class="count">${anomalies.length}</span></h4>
                <div class="anomaly-list">${topAnomalies.map(renderAnomalyCard).join('')}</div>
            </div>` : ''}
        </div>
    </div>`;

    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


/* ============================================================
   DATA TAB
   ============================================================ */

function switchDataTab(tab) {
    dataState.tab = tab;
    dataState.query = '';
    dataState.displayed = 0;
    const searchEl = document.getElementById('data-search');
    if (searchEl) { searchEl.value = ''; searchEl.oninput = () => { dataState.query = searchEl.value.trim().toLowerCase(); dataState.displayed = 0; renderDataTable(); }; }
    document.querySelectorAll('.data-sub-tab').forEach(b => b.classList.toggle('active', b.textContent.toLowerCase().replace(' ', '_').includes(tab)));
    renderDataTable();
}

function renderDataTable() {
    const thead = document.getElementById('data-thead');
    const tbody = document.getElementById('data-tbody');
    const countEl = document.getElementById('data-count');
    const moreBtn = document.getElementById('data-load-more');
    if (!thead || !tbody) return;

    let rows = [], columns = [];

    if (dataState.tab === 'contractors') {
        columns = [
            { key: 'contractor', label: 'Contractor', cls: 'name-cell' },
            { key: 'gross_lakhs', label: 'Spend (₹L)', cls: 'num' },
            { key: 'orders', label: 'Orders', cls: 'num' },
            { key: 'wards', label: 'Wards', cls: 'num' },
            { key: 'anomaly_count', label: 'Flags', cls: 'num' },
            { key: 'risk_score', label: 'Risk', cls: 'num' },
        ];
        rows = Array.isArray(DATA.contractors) ? [...DATA.contractors] : [];
        if (dataState.query) rows = rows.filter(r => (r.contractor || '').toLowerCase().includes(dataState.query));
        rows.sort((a, b) => (b.gross_lakhs || 0) - (a.gross_lakhs || 0));
    } else if (dataState.tab === 'repeat_works') {
        columns = [
            { key: 'ward_name', label: 'Ward', cls: '' },
            { key: 'category', label: 'Category', cls: '' },
            { key: 'fy_count', label: 'FY Count', cls: 'num' },
            { key: 'order_count', label: 'Orders', cls: 'num' },
            { key: 'total_spend_lakhs', label: 'Spend (₹L)', cls: 'num' },
            { key: 'dominant_contractor', label: 'Top Contractor', cls: 'name-cell' },
            { key: 'same_contractor_pct', label: 'Conc %', cls: 'num' },
        ];
        rows = Array.isArray(DATA.repeat_works) ? [...DATA.repeat_works] : [];
        if (dataState.query) rows = rows.filter(r => (r.ward_name || '').toLowerCase().includes(dataState.query) || (r.category || '').toLowerCase().includes(dataState.query));
        rows.sort((a, b) => (b.fy_count || 0) - (a.fy_count || 0));
    } else if (dataState.tab === 'bids') {
        columns = [
            { key: 'ward_name', label: 'Ward', cls: '' },
            { key: 'category', label: 'Category', cls: '' },
            { key: 'amount_lakhs', label: 'Amount (₹L)', cls: 'num' },
            { key: 'ward_median_lakhs', label: 'Median (₹L)', cls: 'num' },
            { key: 'ratio', label: 'Ratio', cls: 'num' },
            { key: 'contractor', label: 'Contractor', cls: 'name-cell' },
        ];
        rows = (DATA.bids || {}).outlier_orders || [];
        rows = [...rows];
        if (dataState.query) rows = rows.filter(r => (r.ward_name || '').toLowerCase().includes(dataState.query) || (r.contractor || '').toLowerCase().includes(dataState.query));
        rows.sort((a, b) => (b.ratio || 0) - (a.ratio || 0));
    } else if (dataState.tab === 'tenders') {
        columns = [
            { key: 'ward', label: 'Ward', cls: 'num' },
            { key: 'title', label: 'Tender Title', cls: 'name-cell' },
            { key: 'value_lakhs', label: 'Value (₹L)', cls: 'num' },
            { key: 'category', label: 'Category', cls: '' },
            { key: 'fy', label: 'FY', cls: '' },
            { key: 'zone', label: 'Zone', cls: '' },
            { key: 'published_date', label: 'Published', cls: '' },
        ];
        const tenders = DATA.tenders || {};
        rows = [...(tenders.records || [])];
        if (dataState.query) {
            const q = dataState.query;
            rows = rows.filter(r => (r.title || '').toLowerCase().includes(q) || (r.zone || '').toLowerCase().includes(q) || String(r.ward || '').includes(q));
        }
        rows.sort((a, b) => (b.value_lakhs || 0) - (a.value_lakhs || 0));
    } else if (dataState.tab === 'tender_gaps') {
        columns = [
            { key: 'ward', label: 'Ward', cls: 'num' },
            { key: 'ward_name', label: 'Ward Name', cls: '' },
            { key: 'zone', label: 'Zone', cls: '' },
            { key: 'fy', label: 'FY', cls: '' },
            { key: 'tender_total_lakhs', label: 'Estimated (₹L)', cls: 'num' },
            { key: 'actual_total_lakhs', label: 'Actual (₹L)', cls: 'num' },
            { key: 'gap_pct', label: 'Gap %', cls: 'num' },
            { key: 'gap_lakhs', label: 'Gap (₹L)', cls: 'num' },
        ];
        const tenders = DATA.tenders || {};
        rows = [...(tenders.gap_analysis || [])];
        if (dataState.query) {
            const q = dataState.query;
            rows = rows.filter(r => (r.ward_name || '').toLowerCase().includes(q) || (r.zone || '').toLowerCase().includes(q) || String(r.ward || '').includes(q));
        }
        rows.sort((a, b) => Math.abs(b.gap_pct || 0) - Math.abs(a.gap_pct || 0));
    } else if (dataState.tab === 'anomalies') {
        columns = [
            { key: 'type', label: 'Type', cls: '' },
            { key: 'severity', label: 'Severity', cls: '' },
            { key: 'score', label: 'Score', cls: 'num' },
            { key: 'ward_name', label: 'Ward', cls: '' },
            { key: 'category', label: 'Category', cls: '' },
            { key: 'description', label: 'Description', cls: 'name-cell' },
        ];
        rows = Array.isArray(DATA.anomalies) ? [...DATA.anomalies] : [];
        if (dataState.query) rows = rows.filter(r => (r.description || '').toLowerCase().includes(dataState.query) || (r.ward_name || '').toLowerCase().includes(dataState.query));
    }

    dataState.filtered = rows;

    // Header
    thead.innerHTML = `<tr>${columns.map(c => `<th class="${c.cls}">${c.label}</th>`).join('')}</tr>`;

    // Body
    const batch = rows.slice(0, dataState.displayed + DATA_PAGE);
    dataState.displayed = batch.length;

    tbody.innerHTML = batch.map(row => {
        const rowClass = dataState.tab === 'contractors' && (row.risk_score || 0) >= 0.6 ? 'row-danger'
            : dataState.tab === 'bids' && (row.ratio || 0) >= 5 ? 'row-danger'
            : dataState.tab === 'tender_gaps' && Math.abs(row.gap_pct || 0) >= 100 ? 'row-danger'
            : dataState.tab === 'anomalies' && row.severity === 'critical' ? 'row-danger'
            : '';
        return `<tr class="${rowClass}">${columns.map(c => {
            let v = row[c.key];
            if (c.key === 'risk_score' && v != null) {
                const rc = v >= 0.6 ? 'risk-crit' : v >= 0.3 ? 'risk-high' : v >= 0.1 ? 'risk-med' : 'risk-low';
                return `<td class="${c.cls}"><span class="risk-badge ${rc}">${Number(v).toFixed(2)}</span></td>`;
            }
            if (c.key === 'severity') {
                return `<td><span class="severity-dot ${v}"></span>${v || ''}</td>`;
            }
            if (c.key === 'type') {
                const m = TYPE_META[v] || {};
                return `<td>${m.icon || ''} ${(m.label || v || '').replace(/_/g, ' ')}</td>`;
            }
            if (c.key === 'gap_pct' && v != null) {
                const absV = Math.abs(v);
                const gapStyle = absV >= 100 ? 'color:var(--critical);font-weight:700' : absV >= 50 ? 'color:var(--high);font-weight:600' : '';
                return `<td class="${c.cls}" style="${gapStyle}">${v > 0 ? '+' : ''}${absV > 9999 ? (v > 0 ? '+9999' : '-9999') : v}%</td>`;
            }
            if (c.key === 'ratio' && v != null) return `<td class="${c.cls}" style="${v >= 3 ? 'color:var(--critical);font-weight:700' : ''}">${Number(v).toFixed(1)}×</td>`;
            if (c.key === 'same_contractor_pct' && v != null) return `<td class="${c.cls}" style="${v >= 70 ? 'color:var(--critical);font-weight:700' : ''}">${v}%</td>`;
            if (c.cls === 'num' && v != null) return `<td class="${c.cls}">${typeof v === 'number' ? v.toLocaleString('en-IN') : v}</td>`;
            if (c.cls === 'name-cell') return `<td class="${c.cls}" title="${esc(String(v || ''))}">${esc(truncate(String(v || ''), 40))}</td>`;
            return `<td class="${c.cls}">${esc(String(v || ''))}</td>`;
        }).join('')}</tr>`;
    }).join('');

    if (countEl) countEl.textContent = `${rows.length.toLocaleString()} rows`;
    if (moreBtn) moreBtn.classList.toggle('hidden', dataState.displayed >= rows.length);
}

function dataLoadMore() {
    renderDataTable();
}

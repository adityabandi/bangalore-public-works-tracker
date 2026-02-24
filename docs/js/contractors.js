/* =====================================================================
   contractors.js  –  Contractors tab: searchable, sortable table
   ===================================================================== */

const CON_PAGE = 100;
let conFiltered = [];
let conDisplayed = 0;
let conSortCol = 'gross_lakhs';
let conSortAsc = false;

function initContractors() {
    const all = DATA.contractors || [];
    conFiltered = [...all];
    renderContractorStats(all);
    renderContractorTable(true);
    wireContractorControls();
}

/* ── stats chips ───────────────────────────────────────── */
function renderContractorStats(all) {
    const el = document.getElementById('contractor-stats');
    if (!el || !all.length) return;

    const totalSpend = all.reduce((s, c) => s + (c.gross_lakhs || 0), 0);
    const totalOrders = all.reduce((s, c) => s + (c.orders || 0), 0);
    const top10Spend = all.slice(0, 10).reduce((s, c) => s + (c.gross_lakhs || 0), 0);
    const top10Pct = totalSpend > 0 ? (top10Spend / totalSpend * 100).toFixed(1) : 0;

    el.innerHTML = `
        <div class="anomaly-stat-chip">
            <span class="anomaly-stat-dot" style="background:#5b8def"></span>
            <span>${all.length.toLocaleString()} contractors</span>
        </div>
        <div class="anomaly-stat-chip">
            <span class="anomaly-stat-dot" style="background:#f59e0b"></span>
            <span>Top 10 control ${top10Pct}% of spend</span>
        </div>
        <div class="anomaly-stat-chip">
            <span class="anomaly-stat-dot" style="background:#22c55e"></span>
            <span>${totalOrders.toLocaleString()} total orders</span>
        </div>`;
}

/* ── table rendering ───────────────────────────────────── */
function renderContractorTable(reset) {
    const tbody = document.getElementById('contractor-tbody');
    const showEl = document.getElementById('contractor-showing');
    const moreBtn = document.getElementById('contractor-load-more');
    if (!tbody) return;

    if (reset) conDisplayed = 0;

    const all = DATA.contractors || [];
    const maxSpend = all.length > 0 ? (all[0].gross_lakhs || 1) : 1;

    const slice = conFiltered.slice(conDisplayed, conDisplayed + CON_PAGE);
    const startRank = conDisplayed;

    const rows = slice.map((c, i) => {
        const rank = startRank + i + 1;
        const pct = maxSpend > 0 ? Math.min(100, (c.gross_lakhs || 0) / maxSpend * 100) : 0;
        return `<tr>
            <td class="col-rank mono">${rank}</td>
            <td class="col-name">${esc(c.contractor)}</td>
            <td class="col-spend mono">₹${fmtL(c.gross_lakhs || 0)}</td>
            <td class="col-orders mono">${(c.orders || 0).toLocaleString()}</td>
            <td class="col-wards mono">${c.wards || 0}</td>
            <td class="col-bar"><div class="con-bar-wrap"><div class="con-bar" style="width:${pct.toFixed(1)}%"></div></div></td>
        </tr>`;
    }).join('');

    if (reset) {
        tbody.innerHTML = rows;
    } else {
        tbody.insertAdjacentHTML('beforeend', rows);
    }

    conDisplayed += slice.length;

    if (showEl) showEl.textContent = `Showing ${conDisplayed.toLocaleString()} of ${conFiltered.length.toLocaleString()} contractors`;
    if (moreBtn) moreBtn.classList.toggle('hidden', conDisplayed >= conFiltered.length);
}

function contractorLoadMore() {
    renderContractorTable(false);
}

/* ── search & sort ─────────────────────────────────────── */
function wireContractorControls() {
    const search = document.getElementById('contractor-search');
    if (search) search.addEventListener('input', () => applyContractorFilters());

    document.querySelectorAll('#contractor-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.col;
            if (conSortCol === col) {
                conSortAsc = !conSortAsc;
            } else {
                conSortCol = col;
                conSortAsc = col === 'contractor'; // ascending for name, desc for numbers
            }
            // Update header icons
            document.querySelectorAll('#contractor-table th.sortable').forEach(h => {
                h.classList.remove('sorted-asc', 'sorted-desc');
                h.querySelector('.sort-icon').textContent = '↕';
            });
            th.classList.add(conSortAsc ? 'sorted-asc' : 'sorted-desc');
            th.querySelector('.sort-icon').textContent = conSortAsc ? '↑' : '↓';

            applyContractorFilters();
        });
    });
}

function applyContractorFilters() {
    const q = ((document.getElementById('contractor-search') || {}).value || '').trim().toLowerCase();
    const all = DATA.contractors || [];

    let filtered = q
        ? all.filter(c => (c.contractor || '').toLowerCase().includes(q))
        : [...all];

    // Sort
    filtered.sort((a, b) => {
        const av = a[conSortCol] || 0;
        const bv = b[conSortCol] || 0;
        if (typeof av === 'string') return conSortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
        return conSortAsc ? av - bv : bv - av;
    });

    conFiltered = filtered;
    renderContractorTable(true);
}

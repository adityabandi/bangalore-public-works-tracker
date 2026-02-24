/* =====================================================================
   repeat_works.js  –  Repeat Works tab: locations re-budgeted year after year
   ===================================================================== */

const RW_PAGE = 50;
let rwFiltered = [];
let rwDisplayed = 0;
let rwSortCol = 'fy_count';
let rwSortAsc = false;

function initRepeatWorks() {
    const all = DATA.repeat_works || [];
    rwFiltered = [...all];
    renderRWStats(all);
    renderRWTable(true);
    wireRWControls();
    renderRWChart(all);
}

function renderRWStats(data) {
    const el = document.getElementById('rw-stats');
    if (!el) return;

    const totalLocations = data.length;
    const totalSpend = data.reduce((s, r) => s + (r.total_spend_lakhs || 0), 0);
    const maxFY = Math.max(...data.map(r => r.fy_count || 0), 0);

    // Worst ward (most repeat clusters)
    const wardCounts = {};
    data.forEach(r => {
        const key = r.ward_name || r.ward;
        wardCounts[key] = (wardCounts[key] || 0) + 1;
    });
    const worstWard = Object.entries(wardCounts).sort((a, b) => b[1] - a[1])[0];

    el.innerHTML = `
        <div class="stat-chip"><span class="stat-value">${totalLocations}</span><span class="stat-label">Repeat Locations</span></div>
        <div class="stat-chip warn"><span class="stat-value">₹${fmtL(totalSpend)}</span><span class="stat-label">Cumulative Spend</span></div>
        <div class="stat-chip danger"><span class="stat-value">${maxFY} FYs</span><span class="stat-label">Longest Repeat</span></div>
        <div class="stat-chip"><span class="stat-value">${worstWard ? worstWard[0] : 'N/A'}</span><span class="stat-label">Worst Ward (${worstWard ? worstWard[1] : 0} repeats)</span></div>
    `;
}

function renderRWTable(reset) {
    if (reset) rwDisplayed = 0;
    const tbody = document.getElementById('rw-tbody');
    if (!tbody) return;
    if (reset) tbody.innerHTML = '';

    const slice = rwFiltered.slice(rwDisplayed, rwDisplayed + RW_PAGE);
    slice.forEach(r => {
        const severity = r.fy_count >= 5 ? 'critical' : r.fy_count >= 4 ? 'high' : 'medium';
        const conPct = r.same_contractor_pct || 0;
        const conClass = conPct >= 70 ? 'rw-high-conc' : '';
        const conName = r.dominant_contractor || (r.contractors && r.contractors.length ? 'Multiple' : '—');
        const conPctClass = conPct >= 70 ? 'danger' : conPct >= 50 ? 'warn' : '';
        const tr = document.createElement('tr');
        tr.className = conClass;
        tr.innerHTML = `
            <td><span class="severity-dot ${severity}"></span>${r.description_sample || ''}</td>
            <td>${r.ward_name || r.ward}</td>
            <td>${r.category || ''}</td>
            <td class="rw-contractor-cell">${esc(conName)}</td>
            <td class="num ${conPctClass}">${conPct > 0 ? conPct + '%' : '—'}</td>
            <td class="num"><strong>${r.fy_count}</strong></td>
            <td class="num">${r.order_count || 0}</td>
            <td class="num">₹${fmtL(r.total_spend_lakhs)}</td>
            <td class="num">₹${fmtL(r.avg_order_lakhs)}</td>
            <td class="fy-list">${(r.fiscal_years || []).join(', ')}</td>
        `;
        tbody.appendChild(tr);
    });
    rwDisplayed += slice.length;

    const btn = document.getElementById('rw-more');
    if (btn) btn.style.display = rwDisplayed >= rwFiltered.length ? 'none' : '';
}

function wireRWControls() {
    const search = document.getElementById('rw-search');
    if (search) {
        search.addEventListener('input', () => {
            const q = search.value.toLowerCase();
            rwFiltered = (DATA.repeat_works || []).filter(r =>
                (r.description_sample || '').toLowerCase().includes(q) ||
                (r.ward_name || '').toLowerCase().includes(q) ||
                (r.category || '').toLowerCase().includes(q)
            );
            sortRW();
            renderRWTable(true);
        });
    }

    const btn = document.getElementById('rw-more');
    if (btn) btn.addEventListener('click', () => renderRWTable(false));

    document.querySelectorAll('#rw-table th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.sort;
            if (rwSortCol === col) rwSortAsc = !rwSortAsc;
            else { rwSortCol = col; rwSortAsc = false; }
            sortRW();
            renderRWTable(true);
        });
    });
}

function sortRW() {
    rwFiltered.sort((a, b) => {
        let va = a[rwSortCol], vb = b[rwSortCol];
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return rwSortAsc ? -1 : 1;
        if (va > vb) return rwSortAsc ? 1 : -1;
        return 0;
    });
}

function renderRWChart(data) {
    const ctx = document.getElementById('rw-chart');
    if (!ctx) return;

    // Top 20 wards by repeat count
    const wardCounts = {};
    data.forEach(r => {
        const key = r.ward_name || r.ward;
        wardCounts[key] = (wardCounts[key] || 0) + r.fy_count;
    });

    const sorted = Object.entries(wardCounts).sort((a, b) => b[1] - a[1]).slice(0, 20);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sorted.map(s => s[0]),
            datasets: [{
                label: 'Total Repeat FY Count',
                data: sorted.map(s => s[1]),
                backgroundColor: sorted.map(s => s[1] >= 15 ? '#f04444' : s[1] >= 8 ? '#f59e0b' : '#5b8def'),
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'Top 20 Wards by Repeat Work Frequency', color: '#e8eaed', font: { size: 14 } }
            },
            scales: {
                x: {
                    grid: { color: '#1e2433' },
                    ticks: { color: '#9aa0b4' }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#9aa0b4', font: { size: 11 } }
                }
            }
        }
    });
}

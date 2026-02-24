/* =====================================================================
   bids.js  –  Bid Analysis tab: benchmark comparison & contractor pricing
   ===================================================================== */

const BID_PAGE = 50;
let bidOutlierFiltered = [];
let bidOutlierDisplayed = 0;
let bidConFiltered = [];
let bidConDisplayed = 0;

function initBids() {
    const bids = DATA.bids || {};
    const cats = bids.categories || [];
    const outliers = bids.outlier_orders || [];
    const pricing = bids.contractor_pricing || [];

    bidOutlierFiltered = [...outliers];
    bidConFiltered = [...pricing];

    renderBidStats(cats, outliers, pricing);
    renderCategoryChart(cats);
    renderOutlierTable(true);
    renderConPricingTable(true);
    wireBidControls();
}

function renderBidStats(cats, outliers, pricing) {
    const el = document.getElementById('bid-stats');
    if (!el) return;

    const totalOutliers = outliers.length;
    const excessSpend = outliers.reduce((s, r) => {
        return s + Math.max(0, (r.amount_lakhs || 0) - (r.ward_median_lakhs || 0));
    }, 0);
    const maxRatio = outliers.length ? Math.max(...outliers.map(r => r.ratio || 0)) : 0;
    const catsWithData = cats.filter(c => c.order_count > 0).length;

    el.innerHTML = `
        <div class="stat-chip danger"><span class="stat-value">${totalOutliers}</span><span class="stat-label">Above-Benchmark Orders</span></div>
        <div class="stat-chip warn"><span class="stat-value">₹${fmtL(excessSpend)}</span><span class="stat-label">Excess over Median</span></div>
        <div class="stat-chip danger"><span class="stat-value">${maxRatio.toFixed(1)}×</span><span class="stat-label">Highest Over-Bid Ratio</span></div>
        <div class="stat-chip"><span class="stat-value">${catsWithData}</span><span class="stat-label">Categories Benchmarked</span></div>
    `;
}

function renderCategoryChart(cats) {
    const ctx = document.getElementById('bid-category-chart');
    if (!ctx || !cats.length) return;

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: cats.map(c => c.category.charAt(0).toUpperCase() + c.category.slice(1)),
            datasets: [
                {
                    label: 'Median Order (₹L)',
                    data: cats.map(c => c.median_order_lakhs),
                    backgroundColor: '#5b8def',
                    borderRadius: 4,
                },
                {
                    label: 'Mean Order (₹L)',
                    data: cats.map(c => c.mean_order_lakhs),
                    backgroundColor: '#f59e0b',
                    borderRadius: 4,
                },
                {
                    label: 'Max Order (₹L)',
                    data: cats.map(c => c.max_order_lakhs),
                    backgroundColor: '#f04444',
                    borderRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: 'Order Cost Distribution by Category', color: '#e8eaed', font: { size: 14 } },
                legend: { labels: { color: '#9aa0b4' } }
            },
            scales: {
                x: {
                    grid: { color: '#1e2433' },
                    ticks: { color: '#9aa0b4' }
                },
                y: {
                    grid: { color: '#1e2433' },
                    ticks: { color: '#9aa0b4' },
                    title: { display: true, text: '₹ Lakhs', color: '#9aa0b4' }
                }
            }
        }
    });
}

function renderOutlierTable(reset) {
    if (reset) bidOutlierDisplayed = 0;
    const tbody = document.getElementById('bid-outlier-tbody');
    if (!tbody) return;
    if (reset) tbody.innerHTML = '';

    const slice = bidOutlierFiltered.slice(bidOutlierDisplayed, bidOutlierDisplayed + BID_PAGE);
    slice.forEach(r => {
        const severity = r.ratio >= 5 ? 'critical' : r.ratio >= 3 ? 'high' : 'medium';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${r.ward_name || r.ward}</td>
            <td>${r.category || ''}</td>
            <td class="num">₹${fmtL(r.amount_lakhs)}</td>
            <td class="num">₹${fmtL(r.ward_median_lakhs)}</td>
            <td class="num"><span class="severity-dot ${severity}"></span><strong>${r.ratio}×</strong></td>
            <td>${r.contractor || ''}</td>
        `;
        tbody.appendChild(tr);
    });
    bidOutlierDisplayed += slice.length;

    const btn = document.getElementById('bid-outlier-more');
    if (btn) btn.style.display = bidOutlierDisplayed >= bidOutlierFiltered.length ? 'none' : '';
}

function renderConPricingTable(reset) {
    if (reset) bidConDisplayed = 0;
    const tbody = document.getElementById('bid-con-tbody');
    if (!tbody) return;
    if (reset) tbody.innerHTML = '';

    const slice = bidConFiltered.slice(bidConDisplayed, bidConDisplayed + BID_PAGE);
    slice.forEach(r => {
        const severity = r.ratio >= 3 ? 'critical' : r.ratio >= 2 ? 'high' : r.ratio >= 1.5 ? 'medium' : 'low';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${r.contractor || ''}</td>
            <td>${r.category || ''}</td>
            <td class="num">₹${fmtL(r.avg_order_lakhs)}</td>
            <td class="num">₹${fmtL(r.category_median_lakhs)}</td>
            <td class="num"><span class="severity-dot ${severity}"></span>${r.ratio}×</td>
            <td class="num">${r.order_count || 0}</td>
            <td class="num">₹${fmtL(r.total_lakhs)}</td>
        `;
        tbody.appendChild(tr);
    });
    bidConDisplayed += slice.length;

    const btn = document.getElementById('bid-con-more');
    if (btn) btn.style.display = bidConDisplayed >= bidConFiltered.length ? 'none' : '';
}

function wireBidControls() {
    const search = document.getElementById('bid-search');
    if (search) {
        search.addEventListener('input', () => {
            const q = search.value.toLowerCase();
            bidOutlierFiltered = ((DATA.bids || {}).outlier_orders || []).filter(r =>
                (r.ward_name || '').toLowerCase().includes(q) ||
                (r.category || '').toLowerCase().includes(q) ||
                (r.contractor || '').toLowerCase().includes(q)
            );
            bidConFiltered = ((DATA.bids || {}).contractor_pricing || []).filter(r =>
                (r.contractor || '').toLowerCase().includes(q) ||
                (r.category || '').toLowerCase().includes(q)
            );
            renderOutlierTable(true);
            renderConPricingTable(true);
        });
    }

    const btn1 = document.getElementById('bid-outlier-more');
    if (btn1) btn1.addEventListener('click', () => renderOutlierTable(false));
    const btn2 = document.getElementById('bid-con-more');
    if (btn2) btn2.addEventListener('click', () => renderConPricingTable(false));
}

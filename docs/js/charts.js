/* =====================================================================
   charts.js  –  Chart.js charts for overview & analytics tabs
   ===================================================================== */

const CHART_COLORS = [
    '#5b8def','#f59e0b','#22c55e','#f04444','#a78bfa',
    '#ec4899','#06b6d4','#84cc16','#f97316','#64748b',
    '#e879f9','#14b8a6','#fb923c','#818cf8','#facc15'
];

const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { labels: { color: '#9aa0b4', font: { family: 'Inter', size: 11 }, boxWidth: 10, padding: 12 } },
        tooltip: {
            backgroundColor: '#1c2030',
            titleColor: '#e8eaed',
            bodyColor: '#9aa0b4',
            borderColor: '#262d3d',
            borderWidth: 1,
            cornerRadius: 6,
            padding: 10,
            bodyFont: { family: 'Inter', size: 12 },
            titleFont: { family: 'Inter', size: 12, weight: 600 },
            callbacks: { label: ctx => ` ${ctx.dataset.label || ctx.label}: ₹${Number(ctx.raw||0).toFixed(1)}L` }
        }
    },
    scales: {
        x: { ticks: { color: '#5f6680', font: { size: 10 } }, grid: { color: '#1e2433' } },
        y: { ticks: { color: '#5f6680', font: { size: 10 } }, grid: { color: '#1e2433' } }
    }
};

const charts = {};

function initCharts() {
    renderCategoryChart();
    renderYearlyChart();
    renderContractorsChart();
    renderAnomalyTypesChart();
    renderCategoryTrendChart();
    renderWardSpendChart();
}

/* ── 1. Category Doughnut (Overview) ──────────────────── */
function renderCategoryChart() {
    const el = document.getElementById('chart-category');
    if (!el) return;
    const s = DATA.summary || {};
    const cats = s.by_category || {};
    const sorted = Object.entries(cats).sort((a,b) => b[1]-a[1]).slice(0, 10);
    if (!sorted.length) return;

    charts.category = new Chart(el, {
        type: 'doughnut',
        data: {
            labels: sorted.map(c => c[0]),
            datasets: [{ data: sorted.map(c => c[1]), backgroundColor: CHART_COLORS.slice(0, sorted.length), borderWidth: 0 }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '65%',
            plugins: {
                legend: { position: 'right', labels: { color: '#9aa0b4', font: { family: 'Inter', size: 10 }, boxWidth: 8, padding: 8 } },
                tooltip: { ...CHART_DEFAULTS.plugins.tooltip }
            }
        }
    });
}

/* ── 2. Yearly Bar+Line (Overview) ────────────────────── */
function renderYearlyChart() {
    const el = document.getElementById('chart-yearly');
    if (!el) return;
    const ts = DATA.timeseries || {};
    const years = Object.keys(ts).sort();
    if (!years.length) return;

    const spend = years.map(y => ts[y].gross_lakhs || 0);
    const orders = years.map(y => ts[y].count || 0);

    charts.yearly = new Chart(el, {
        type: 'bar',
        data: {
            labels: years,
            datasets: [
                { label: 'Spend (₹L)', data: spend, backgroundColor: '#5b8def88', borderColor: '#5b8def', borderWidth: 1, borderRadius: 4, yAxisID: 'y' },
                { label: 'Orders', data: orders, type: 'line', borderColor: '#f59e0b', pointBackgroundColor: '#f59e0b', pointRadius: 3, tension: 0.3, yAxisID: 'y1' }
            ]
        },
        options: {
            ...CHART_DEFAULTS,
            scales: {
                x: CHART_DEFAULTS.scales.x,
                y: { ...CHART_DEFAULTS.scales.y, title: { display: true, text: 'Spend (₹L)', color: '#5f6680', font: { size: 10 } } },
                y1: { position: 'right', ticks: { color: '#5f6680', font: { size: 10 } }, grid: { drawOnChartArea: false }, title: { display: true, text: 'Orders', color: '#5f6680', font: { size: 10 } } }
            },
            plugins: { ...CHART_DEFAULTS.plugins, tooltip: { ...CHART_DEFAULTS.plugins.tooltip, callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.datasetIndex === 0 ? '₹'+Number(ctx.raw).toFixed(0)+'L' : ctx.raw}` } } }
        }
    });
}

/* ── 3. Top Contractors (Analytics) ───────────────────── */
function renderContractorsChart() {
    const el = document.getElementById('chart-contractors');
    if (!el) return;
    const c = DATA.contractors || [];
    const top = c.slice(0, 15);
    if (!top.length) return;

    charts.contractors = new Chart(el, {
        type: 'bar',
        data: {
            labels: top.map(c => truncate(c.contractor || c.name, 30)),
            datasets: [{ label: 'Spend (₹L)', data: top.map(c => c.gross_lakhs || c.total_gross_lakhs || 0), backgroundColor: '#5b8def88', borderColor: '#5b8def', borderWidth: 1, borderRadius: 3 }]
        },
        options: {
            ...CHART_DEFAULTS, indexAxis: 'y',
            plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } },
            scales: {
                x: { ...CHART_DEFAULTS.scales.x, title: { display: true, text: 'Spend (₹L)', color: '#5f6680', font: { size: 10 } } },
                y: { ticks: { color: '#9aa0b4', font: { size: 10 } }, grid: { display: false } }
            }
        }
    });
}

/* ── 4. Anomaly Types (Analytics) ─────────────────────── */
function renderAnomalyTypesChart() {
    const el = document.getElementById('chart-anomaly-types');
    if (!el) return;
    const anomalies = DATA.anomalies || [];
    if (!anomalies.length) return;

    const typeCounts = {};
    const sevByType = {};
    anomalies.forEach(a => {
        const t = (a.type || 'unknown').replace(/_/g, ' ');
        typeCounts[t] = (typeCounts[t] || 0) + 1;
        if (!sevByType[t]) sevByType[t] = { critical: 0, high: 0, medium: 0, low: 0 };
        sevByType[t][a.severity || 'medium']++;
    });

    const types = Object.keys(typeCounts).sort((a,b) => typeCounts[b] - typeCounts[a]);
    const sevColors = { critical: '#f04444', high: '#f59e0b', medium: '#8b8fa3', low: '#22c55e' };

    charts.anomalyTypes = new Chart(el, {
        type: 'bar',
        data: {
            labels: types,
            datasets: ['critical','high','medium','low'].map(s => ({
                label: s.charAt(0).toUpperCase() + s.slice(1),
                data: types.map(t => (sevByType[t] || {})[s] || 0),
                backgroundColor: sevColors[s] + '99',
                borderColor: sevColors[s],
                borderWidth: 1,
                borderRadius: 2
            }))
        },
        options: {
            ...CHART_DEFAULTS,
            scales: {
                x: { ...CHART_DEFAULTS.scales.x, stacked: true },
                y: { ...CHART_DEFAULTS.scales.y, stacked: true }
            },
            plugins: {
                ...CHART_DEFAULTS.plugins,
                tooltip: { ...CHART_DEFAULTS.plugins.tooltip, callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.raw}` } }
            }
        }
    });
}

/* ── 5. Category Trend (Analytics) ────────────────────── */
function renderCategoryTrendChart() {
    const el = document.getElementById('chart-category-trend');
    if (!el) return;
    const ts = DATA.timeseries || {};
    const years = Object.keys(ts).sort();
    if (!years.length) return;

    // Gather all categories across years
    const catSet = new Set();
    years.forEach(y => {
        Object.keys(ts[y].by_category || {}).forEach(c => catSet.add(c));
    });
    const topCats = [...catSet].map(c => ({
        name: c,
        total: years.reduce((s, y) => s + ((ts[y].by_category || {})[c] || 0), 0)
    })).sort((a,b) => b.total - a.total).slice(0, 8);

    charts.catTrend = new Chart(el, {
        type: 'line',
        data: {
            labels: years,
            datasets: topCats.map((c, i) => ({
                label: c.name,
                data: years.map(y => ((ts[y].by_category || {})[c.name] || 0)),
                borderColor: CHART_COLORS[i],
                backgroundColor: CHART_COLORS[i] + '22',
                fill: true,
                tension: 0.3,
                pointRadius: 2,
                borderWidth: 1.5
            }))
        },
        options: {
            ...CHART_DEFAULTS,
            plugins: { ...CHART_DEFAULTS.plugins, tooltip: { ...CHART_DEFAULTS.plugins.tooltip, mode: 'index', intersect: false } }
        }
    });
}

/* ── 6. Ward Spend (Analytics) ────────────────────────── */
function renderWardSpendChart() {
    const el = document.getElementById('chart-ward-spend');
    if (!el) return;
    const wards = DATA.wards || {};
    const sorted = Object.entries(wards)
        .map(([k,v]) => ({ ward: v.ward_name || `Ward ${k}`, spend: v.total_gross_lakhs || 0 }))
        .sort((a,b) => b.spend - a.spend)
        .slice(0, 20);
    if (!sorted.length) return;

    charts.wardSpend = new Chart(el, {
        type: 'bar',
        data: {
            labels: sorted.map(w => truncate(w.ward, 25)),
            datasets: [{ label: 'Spend (₹L)', data: sorted.map(w => w.spend), backgroundColor: '#5b8def55', borderColor: '#5b8def', borderWidth: 1, borderRadius: 3 }]
        },
        options: {
            ...CHART_DEFAULTS, indexAxis: 'y',
            plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } },
            scales: {
                x: { ...CHART_DEFAULTS.scales.x, title: { display: true, text: 'Spend (₹L)', color: '#5f6680', font: { size: 10 } } },
                y: { ticks: { color: '#9aa0b4', font: { size: 9 } }, grid: { display: false } }
            }
        }
    });
}

/* ── util ──────────────────────────────────────────────── */
function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : (s || ''); }

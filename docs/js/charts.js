/* =====================================================================
   charts.js  –  Dashboard charts (money flow + category donut)
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
        }
    },
    scales: {
        x: { ticks: { color: '#5f6680', font: { size: 10 } }, grid: { color: '#1e2433' } },
        y: { ticks: { color: '#5f6680', font: { size: 10 } }, grid: { color: '#1e2433' } }
    }
};

const charts = {};

function initCharts() {
    renderFlowChart();
    renderCategoryDonut();
}

/* ── 1. Money Flow — Stacked Bar by FY ────────────────── */
function renderFlowChart() {
    const el = document.getElementById('chart-flow');
    if (!el) return;
    const ts = DATA.timeseries || {};
    const years = Object.keys(ts).sort();
    if (!years.length) return;

    // Build stacked datasets by top categories
    const catSet = new Set();
    years.forEach(y => Object.keys(ts[y].by_category || {}).forEach(c => catSet.add(c)));
    const topCats = [...catSet].map(c => ({
        name: c,
        total: years.reduce((s, y) => s + ((ts[y].by_category || {})[c] || 0), 0)
    })).sort((a, b) => b.total - a.total).slice(0, 8);

    const otherLabel = 'Other';

    const datasets = topCats.map((c, i) => ({
        label: c.name,
        data: years.map(y => ((ts[y].by_category || {})[c.name] || 0)),
        backgroundColor: CHART_COLORS[i] + 'cc',
        borderColor: CHART_COLORS[i],
        borderWidth: 1,
        borderRadius: 2,
    }));

    // "Other" bucket
    const otherData = years.map(y => {
        const byC = ts[y].by_category || {};
        const topSet = new Set(topCats.map(c => c.name));
        return Object.entries(byC).reduce((s, [k, v]) => s + (topSet.has(k) ? 0 : v), 0);
    });
    if (otherData.some(v => v > 0)) {
        datasets.push({
            label: otherLabel,
            data: otherData,
            backgroundColor: '#3a3f52cc',
            borderColor: '#3a3f52',
            borderWidth: 1,
            borderRadius: 2,
        });
    }

    charts.flow = new Chart(el, {
        type: 'bar',
        data: { labels: years, datasets },
        options: {
            ...CHART_DEFAULTS,
            scales: {
                x: { ...CHART_DEFAULTS.scales.x, stacked: true },
                y: {
                    ...CHART_DEFAULTS.scales.y, stacked: true,
                    title: { display: true, text: 'Spend (₹ Lakhs)', color: '#5f6680', font: { size: 10 } }
                }
            },
            plugins: {
                ...CHART_DEFAULTS.plugins,
                legend: { position: 'bottom', labels: { color: '#9aa0b4', font: { family: 'Inter', size: 10 }, boxWidth: 8, padding: 10 } },
                tooltip: {
                    ...CHART_DEFAULTS.plugins.tooltip,
                    mode: 'index',
                    intersect: false,
                    callbacks: { label: ctx => ` ${ctx.dataset.label}: ₹${Number(ctx.raw || 0).toLocaleString('en-IN')}L` }
                }
            }
        }
    });
}

/* ── 2. Category Donut ────────────────────────────────── */
function renderCategoryDonut() {
    const el = document.getElementById('chart-category-donut');
    if (!el) return;
    const s = DATA.summary || {};
    const cats = s.by_category || {};
    const sorted = Object.entries(cats).sort((a, b) => b[1] - a[1]);
    if (!sorted.length) return;

    const top = sorted.slice(0, 10);
    const otherVal = sorted.slice(10).reduce((s, [, v]) => s + v, 0);
    const labels = top.map(c => c[0]);
    const values = top.map(c => c[1]);
    if (otherVal > 0) { labels.push('Other'); values.push(otherVal); }

    const bg = labels.map((_, i) => i < CHART_COLORS.length ? CHART_COLORS[i] : '#3a3f52');

    charts.categoryDonut = new Chart(el, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{ data: values, backgroundColor: bg, borderWidth: 0, hoverOffset: 6 }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#9aa0b4', font: { family: 'Inter', size: 10 }, boxWidth: 8, padding: 8 }
                },
                tooltip: {
                    ...CHART_DEFAULTS.plugins.tooltip,
                    callbacks: {
                        label: ctx => {
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total ? ((ctx.raw / total) * 100).toFixed(1) : 0;
                            return ` ${ctx.label}: ₹${Number(ctx.raw).toLocaleString('en-IN')}L (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

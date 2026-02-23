/**
 * Chart.js visualizations for spending analytics.
 */

const Charts = {
    charts: {},

    init(summary, contractors, timeseries) {
        // Set Chart.js defaults for dark theme
        Chart.defaults.color = '#8b8fa3';
        Chart.defaults.borderColor = '#2d3140';
        Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

        if (summary) {
            this.renderCategoryChart(summary.by_category);
            this.renderAnomalyTypesChart(summary.anomaly_summary);
        }
        if (contractors) {
            this.renderContractorsChart(contractors);
        }
        if (timeseries) {
            this.renderYearlyChart(timeseries.yearly);
        }
    },

    renderCategoryChart(byCategory) {
        if (!byCategory) return;
        const ctx = document.getElementById('chart-category');
        if (!ctx) return;

        const entries = Object.entries(byCategory).sort((a, b) => b[1].gross_lakhs - a[1].gross_lakhs);
        const labels = entries.map(([k]) => k.charAt(0).toUpperCase() + k.slice(1));
        const values = entries.map(([, v]) => v.gross_lakhs);

        const colors = [
            '#4a9eff', '#f97316', '#22c55e', '#eab308',
            '#ef4444', '#a855f7', '#ec4899', '#06b6d4',
        ];

        this.charts.category = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors.slice(0, labels.length),
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { padding: 12, usePointStyle: true, pointStyleWidth: 10 },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const val = ctx.parsed;
                                if (val >= 100) return ` ${ctx.label}: \u20B9${(val / 100).toFixed(1)} Cr`;
                                return ` ${ctx.label}: \u20B9${val.toFixed(1)} L`;
                            },
                        },
                    },
                },
            },
        });
    },

    renderContractorsChart(contractors) {
        if (!contractors) return;
        const ctx = document.getElementById('chart-contractors');
        if (!ctx) return;

        const entries = Object.values(contractors)
            .sort((a, b) => b.total_gross_lakhs - a.total_gross_lakhs)
            .slice(0, 10);

        const labels = entries.map(c => {
            const name = c.name || '';
            return name.length > 25 ? name.substring(0, 25) + '...' : name;
        });
        const values = entries.map(c => c.total_gross_lakhs);
        const anomalyCounts = entries.map(c => c.anomaly_count || 0);

        this.charts.contractors = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Total Spend (Lakhs)',
                    data: values,
                    backgroundColor: values.map((_, i) =>
                        anomalyCounts[i] > 5 ? '#ef4444' :
                        anomalyCounts[i] > 2 ? '#f97316' : '#4a9eff'
                    ),
                    borderWidth: 0,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            afterLabel: (ctx) => {
                                const c = entries[ctx.dataIndex];
                                return `Orders: ${c.total_orders} | Flags: ${c.anomaly_count}`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { color: '#2d3140' },
                        ticks: {
                            callback: (v) => v >= 100 ? (v / 100).toFixed(0) + ' Cr' : v + ' L',
                        },
                    },
                    y: {
                        grid: { display: false },
                        ticks: { font: { size: 10 } },
                    },
                },
            },
        });
    },

    renderYearlyChart(yearly) {
        if (!yearly) return;
        const ctx = document.getElementById('chart-yearly');
        if (!ctx) return;

        const entries = Object.entries(yearly).sort();
        const labels = entries.map(([fy]) => fy);
        const values = entries.map(([, v]) => v.total_lakhs);
        const counts = entries.map(([, v]) => v.count);

        this.charts.yearly = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Spend (Lakhs)',
                    data: values,
                    backgroundColor: '#4a9eff',
                    borderWidth: 0,
                    borderRadius: 4,
                    yAxisID: 'y',
                }, {
                    label: 'Work Orders',
                    data: counts,
                    type: 'line',
                    borderColor: '#f97316',
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    pointRadius: 4,
                    pointBackgroundColor: '#f97316',
                    yAxisID: 'y1',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: { labels: { usePointStyle: true } },
                },
                scales: {
                    x: { grid: { color: '#2d3140' } },
                    y: {
                        grid: { color: '#2d3140' },
                        position: 'left',
                        ticks: {
                            callback: (v) => v >= 100 ? (v / 100).toFixed(0) + ' Cr' : v + ' L',
                        },
                    },
                    y1: {
                        grid: { display: false },
                        position: 'right',
                    },
                },
            },
        });
    },

    renderAnomalyTypesChart(anomalySummary) {
        if (!anomalySummary) return;
        const ctx = document.getElementById('chart-anomaly-types');
        if (!ctx) return;

        const typeLabels = {
            cost_outlier: 'Cost Outliers',
            contractor_concentration: 'Contractor Conc.',
            duplicate_work: 'Duplicates',
            payment_speed: 'Fast Payments',
            deduction_ratio: 'Deduction Ratio',
            benford_violation: 'Benford Violation',
        };

        const entries = Object.entries(anomalySummary);
        const labels = entries.map(([k]) => typeLabels[k] || k);
        const totals = entries.map(([, v]) => v.count);
        const critical = entries.map(([, v]) => v.critical || 0);
        const high = entries.map(([, v]) => v.high || 0);

        this.charts.anomalyTypes = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Critical',
                        data: critical,
                        backgroundColor: '#ef4444',
                        borderWidth: 0,
                        borderRadius: 2,
                    },
                    {
                        label: 'High',
                        data: high,
                        backgroundColor: '#f97316',
                        borderWidth: 0,
                        borderRadius: 2,
                    },
                    {
                        label: 'Other',
                        data: totals.map((t, i) => t - critical[i] - high[i]),
                        backgroundColor: '#4a9eff',
                        borderWidth: 0,
                        borderRadius: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: { labels: { usePointStyle: true } },
                },
                scales: {
                    x: {
                        grid: { color: '#2d3140' },
                        stacked: true,
                        ticks: { font: { size: 10 } },
                    },
                    y: {
                        grid: { color: '#2d3140' },
                        stacked: true,
                    },
                },
            },
        });
    },
};

/**
 * Main application: load data, initialize all components.
 */

const App = {
    data: {},

    async init() {
        try {
            await this.loadData();
            this.renderHeader();
            MapView.init(this.data.wards);
            AnomalyFeed.init(this.data.anomalies);
            Charts.init(this.data.summary, this.data.contractors, this.data.timeseries);
        } catch (err) {
            console.error('Failed to initialize:', err);
            document.querySelector('main').innerHTML =
                '<div class="loading" style="flex-direction:column;gap:1rem;">' +
                '<p>Failed to load data. Run the pipeline first to generate JSON files.</p>' +
                '<code style="font-size:0.8rem;color:var(--text-muted)">' + err.message + '</code>' +
                '</div>';
        }
    },

    async loadData() {
        const files = ['meta', 'summary', 'wards', 'anomalies', 'contractors', 'timeseries'];
        const results = await Promise.all(
            files.map(f =>
                fetch(`data/${f}.json?t=${Date.now()}`)
                    .then(r => {
                        if (!r.ok) throw new Error(`${f}.json: ${r.status}`);
                        return r.json();
                    })
            )
        );
        files.forEach((name, i) => { this.data[name] = results[i]; });
    },

    renderHeader() {
        const meta = this.data.meta;
        if (!meta) return;

        const el = (id, val) => {
            const node = document.getElementById(id);
            if (node) node.textContent = val;
        };

        el('stat-records', this.formatNumber(meta.total_records));
        el('stat-spend', this.formatCrores(meta.total_spend_crores));
        el('stat-anomalies', this.formatNumber(meta.anomalies_detected));
        el('stat-updated', this.formatDate(meta.last_updated));
    },

    formatNumber(n) {
        if (n == null) return '--';
        if (n >= 100000) return (n / 100000).toFixed(1) + 'L';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return n.toLocaleString('en-IN');
    },

    formatCrores(cr) {
        if (cr == null) return '--';
        return '\u20B9' + cr.toLocaleString('en-IN', { maximumFractionDigits: 0 }) + ' Cr';
    },

    formatLakhs(lakhs) {
        if (lakhs == null) return '--';
        if (lakhs >= 100) return '\u20B9' + (lakhs / 100).toFixed(1) + ' Cr';
        return '\u20B9' + lakhs.toFixed(1) + ' L';
    },

    formatDate(iso) {
        if (!iso) return '--';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
        } catch { return '--'; }
    }
};

document.addEventListener('DOMContentLoaded', () => App.init());

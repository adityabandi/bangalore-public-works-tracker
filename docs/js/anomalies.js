/**
 * Anomaly feed renderer with filtering and search.
 */

const AnomalyFeed = {
    allAnomalies: [],
    filtered: [],
    displayCount: 50,
    batchSize: 50,

    init(anomalies) {
        this.allAnomalies = anomalies || [];
        this.filtered = [...this.allAnomalies];
        this.setupFilters();
        this.render();
    },

    setupFilters() {
        const typeFilter = document.getElementById('filter-type');
        const severityFilter = document.getElementById('filter-severity');
        const searchInput = document.getElementById('filter-search');
        const loadMore = document.getElementById('load-more');

        if (typeFilter) typeFilter.addEventListener('change', () => this.applyFilters());
        if (severityFilter) severityFilter.addEventListener('change', () => this.applyFilters());
        if (searchInput) {
            let debounceTimer;
            searchInput.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => this.applyFilters(), 300);
            });
        }
        if (loadMore) loadMore.addEventListener('click', () => this.loadMore());
    },

    applyFilters() {
        const type = document.getElementById('filter-type')?.value || 'all';
        const severity = document.getElementById('filter-severity')?.value || 'all';
        const search = (document.getElementById('filter-search')?.value || '').toLowerCase().trim();

        this.filtered = this.allAnomalies.filter(a => {
            if (type !== 'all' && a.type !== type) return false;
            if (severity !== 'all' && a.severity_label !== severity) return false;
            if (search) {
                const text = `${a.description} ${a.ward_name} ${a.contractor} ${a.fiscal_year}`.toLowerCase();
                if (!text.includes(search)) return false;
            }
            return true;
        });

        this.displayCount = this.batchSize;
        this.render();
    },

    render() {
        const feed = document.getElementById('anomaly-feed');
        const loadMore = document.getElementById('load-more');
        if (!feed) return;

        const toShow = this.filtered.slice(0, this.displayCount);

        if (toShow.length === 0) {
            feed.innerHTML = '<div class="loading" style="animation:none;">No anomalies match your filters.</div>';
            if (loadMore) loadMore.classList.add('hidden');
            return;
        }

        feed.innerHTML = toShow.map(a => this.renderCard(a)).join('');

        if (loadMore) {
            if (this.displayCount < this.filtered.length) {
                loadMore.classList.remove('hidden');
                loadMore.textContent = `Load More (${this.filtered.length - this.displayCount} remaining)`;
            } else {
                loadMore.classList.add('hidden');
            }
        }
    },

    loadMore() {
        this.displayCount += this.batchSize;
        this.render();
    },

    renderCard(a) {
        const typeLabels = {
            cost_outlier: 'Cost',
            contractor_concentration: 'Contractor',
            duplicate_work: 'Duplicate',
            payment_speed: 'Speed',
            deduction_ratio: 'Deduction',
            benford_violation: 'Benford',
        };

        const badgeClass = `badge-${a.severity_label || 'low'}`;
        const typeLabel = typeLabels[a.type] || a.type;

        return `
            <div class="anomaly-card">
                <span class="anomaly-badge ${badgeClass}">${a.severity_label || 'low'}</span>
                <div class="anomaly-content">
                    <div class="anomaly-desc">${this.escapeHtml(a.description)}</div>
                    <div class="anomaly-meta">
                        <span class="anomaly-type-tag">${typeLabel}</span>
                        ${a.ward_name ? `<span>Ward: ${this.escapeHtml(a.ward_name)}</span>` : ''}
                        ${a.contractor ? `<span>${this.escapeHtml(a.contractor)}</span>` : ''}
                        ${a.fiscal_year ? `<span>${a.fiscal_year}</span>` : ''}
                    </div>
                </div>
            </div>
        `;
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },
};

/**
 * Leaflet ward choropleth map colored by anomaly score.
 */

const MapView = {
    map: null,
    geoLayer: null,
    wardData: null,

    init(wardData) {
        this.wardData = wardData || {};

        this.map = L.map('map', {
            zoomControl: true,
            scrollWheelZoom: true,
        }).setView([12.9716, 77.5946], 11);

        // Dark tile layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://carto.com/">CARTO</a> | &copy; <a href="https://www.openstreetmap.org/">OSM</a>',
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(this.map);

        this.loadGeoJSON();
    },

    async loadGeoJSON() {
        try {
            const resp = await fetch('assets/bbmp_wards.geojson');
            if (!resp.ok) {
                this.showMapMessage('Ward boundary GeoJSON not found. Add bbmp_wards.geojson to docs/assets/');
                return;
            }
            const geojson = await resp.json();
            this.renderChoropleth(geojson);
        } catch (err) {
            this.showMapMessage('Failed to load ward boundaries: ' + err.message);
        }
    },

    renderChoropleth(geojson) {
        this.geoLayer = L.geoJSON(geojson, {
            style: (feature) => this.getStyle(feature),
            onEachFeature: (feature, layer) => {
                const wardNum = this.extractWardNum(feature);
                const ward = wardNum ? this.wardData[String(wardNum)] : null;
                const name = ward ? ward.name : `Ward ${wardNum || '?'}`;

                layer.bindTooltip(name, {
                    sticky: true,
                    className: 'ward-tooltip',
                });

                layer.on('click', () => this.showWardDetail(wardNum, ward));
            },
        }).addTo(this.map);

        // Fit to bounds
        if (this.geoLayer.getBounds().isValid()) {
            this.map.fitBounds(this.geoLayer.getBounds(), { padding: [20, 20] });
        }

        // Add legend
        this.addLegend();
    },

    getStyle(feature) {
        const wardNum = this.extractWardNum(feature);
        const ward = wardNum ? this.wardData[String(wardNum)] : null;
        const score = ward ? ward.anomaly_score : 0;

        return {
            fillColor: this.getColor(score),
            weight: 1,
            opacity: 0.8,
            color: '#444',
            fillOpacity: 0.7,
        };
    },

    getColor(score) {
        if (score >= 0.8) return '#ef4444';
        if (score >= 0.6) return '#f97316';
        if (score >= 0.4) return '#eab308';
        if (score >= 0.2) return '#22c55e';
        return '#166534';
    },

    extractWardNum(feature) {
        const props = feature.properties || {};
        // Try common property names from datameet GeoJSON
        for (const key of ['ward_no', 'Ward_No', 'WARD_NO', 'ward_num', 'Ward_Num', 'id', 'ID']) {
            if (props[key] != null) {
                const n = parseInt(props[key], 10);
                if (!isNaN(n) && n > 0 && n <= 300) return n;
            }
        }
        // Try name-based extraction
        const name = props.name || props.Name || props.WARD_NAME || '';
        const m = name.match(/^(\d+)/);
        if (m) return parseInt(m[1], 10);
        return null;
    },

    showWardDetail(wardNum, ward) {
        const panel = document.getElementById('ward-detail');
        const title = document.getElementById('ward-detail-title');
        const content = document.getElementById('ward-detail-content');

        if (!ward) {
            title.textContent = `Ward ${wardNum || '?'}`;
            content.innerHTML = '<p style="color:var(--text-muted)">No data available for this ward.</p>';
            panel.classList.remove('hidden');
            return;
        }

        title.textContent = ward.name;

        let html = '';

        // Stats
        const stats = [
            ['Total Orders', ward.total_orders.toLocaleString('en-IN')],
            ['Total Spend', App.formatLakhs(ward.total_gross_lakhs)],
            ['Anomalies', ward.anomaly_count],
            ['Anomaly Score', (ward.anomaly_score * 100).toFixed(0) + '%'],
            ['Zone', ward.zone || '--'],
        ];
        stats.forEach(([label, val]) => {
            html += `<div class="ward-stat"><span class="ward-stat-label">${label}</span><span class="ward-stat-value">${val}</span></div>`;
        });

        // Category breakdown
        if (ward.by_category) {
            html += '<div class="ward-contractor-list"><h4>By Category</h4>';
            Object.entries(ward.by_category)
                .sort((a, b) => b[1] - a[1])
                .forEach(([cat, count]) => {
                    html += `<div class="ward-contractor-item"><span>${cat}</span><span>${count}</span></div>`;
                });
            html += '</div>';
        }

        // Top contractors
        if (ward.top_contractors && ward.top_contractors.length > 0) {
            html += '<div class="ward-contractor-list"><h4>Top Contractors</h4>';
            ward.top_contractors.forEach(c => {
                html += `<div class="ward-contractor-item"><span>${c.name}</span><span>${c.orders} orders | ${App.formatLakhs(c.value_lakhs)}</span></div>`;
            });
            html += '</div>';
        }

        content.innerHTML = html;
        panel.classList.remove('hidden');
    },

    addLegend() {
        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = function () {
            const div = L.DomUtil.create('div', 'legend');
            div.style.cssText = 'background:rgba(26,29,39,0.9);padding:10px 14px;border-radius:6px;border:1px solid #2d3140;font-size:11px;color:#e4e6eb;line-height:1.8;';
            div.innerHTML = '<strong>Anomaly Score</strong><br>' +
                '<span style="background:#ef4444;width:12px;height:12px;display:inline-block;border-radius:2px;margin-right:6px;vertical-align:middle;"></span>Critical (&ge;80%)<br>' +
                '<span style="background:#f97316;width:12px;height:12px;display:inline-block;border-radius:2px;margin-right:6px;vertical-align:middle;"></span>High (60-79%)<br>' +
                '<span style="background:#eab308;width:12px;height:12px;display:inline-block;border-radius:2px;margin-right:6px;vertical-align:middle;"></span>Medium (40-59%)<br>' +
                '<span style="background:#22c55e;width:12px;height:12px;display:inline-block;border-radius:2px;margin-right:6px;vertical-align:middle;"></span>Low (20-39%)<br>' +
                '<span style="background:#166534;width:12px;height:12px;display:inline-block;border-radius:2px;margin-right:6px;vertical-align:middle;"></span>Minimal (&lt;20%)';
            return div;
        };
        legend.addTo(this.map);
    },

    showMapMessage(msg) {
        document.getElementById('map').innerHTML =
            `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);padding:2rem;text-align:center;">${msg}</div>`;
    },
};

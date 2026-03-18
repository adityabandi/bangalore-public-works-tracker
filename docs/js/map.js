/* =====================================================================
   map.js  –  Leaflet choropleth (light theme)
   ===================================================================== */

let map, geoLayer, wardLookup = {};
const METRICS = {
    anomaly_score:     { label: 'Anomaly Score', fmt: v => (v||0).toFixed(2), palette: ['#DCFCE7','#F59E0B','#DC2626'] },
    total_gross_lakhs: { label: 'Total Spend (₹L)', fmt: v => fmtL(v||0), palette: ['#DBEAFE','#2563EB','#1E3A8A'] },
    anomaly_count:     { label: 'Anomalies', fmt: v => String(v||0), palette: ['#FEF3C7','#F59E0B','#DC2626'] },
    total_orders:      { label: 'Total Orders', fmt: v => String(v||0), palette: ['#E0E7FF','#6366F1','#312E81'] }
};

function initMap() {
    if (!document.getElementById('map')) return;

    buildWardLookup();

    map = L.map('map', {
        center: [12.9716, 77.5946],
        zoom: 11,
        zoomControl: false,
        attributionControl: false
    });

    L.control.zoom({ position: 'topright' }).addTo(map);
    L.control.attribution({ position: 'bottomright', prefix: false })
        .addAttribution('© <a href="https://www.openstreetmap.org/copyright">OSM</a>')
        .addTo(map);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 18, subdomains: 'abcd'
    }).addTo(map);

    loadGeo();
    wireControls();
}

function buildWardLookup() {
    const wards = DATA.wards || {};
    wardLookup = {};
    Object.entries(wards).forEach(([k, v]) => {
        wardLookup[String(k)] = v;
    });
}

async function loadGeo() {
    try {
        const r = await fetch('assets/bbmp_wards.geojson');
        const geo = await r.json();
        renderGeo(geo);
    } catch (e) {
        console.error('GeoJSON load error:', e);
    }
}

function renderGeo(geo) {
    const metric = getMetric();
    const vals = geo.features.map(f => {
        const w = wardLookup[String(f.properties.WARD_NO)] || {};
        return metric === 'anomaly_score' ? (w.anomaly_score || 0)
             : metric === 'total_gross_lakhs' ? (w.total_gross_lakhs || 0)
             : metric === 'anomaly_count' ? (w.anomaly_count || 0)
             : (w.total_orders || 0);
    });
    const mn = Math.min(...vals), mx = Math.max(...vals) || 1;

    if (geoLayer) map.removeLayer(geoLayer);

    geoLayer = L.geoJSON(geo, {
        style: f => {
            const w = wardLookup[String(f.properties.WARD_NO)] || {};
            const v = getVal(w, metric);
            return {
                fillColor: colorScale(v, mn, mx, METRICS[metric].palette),
                weight: 1,
                color: '#D1D5DB',
                fillOpacity: 0.8
            };
        },
        onEachFeature: (f, layer) => {
            const wn = String(f.properties.WARD_NO);
            const w = wardLookup[wn] || {};
            const name = w.ward_name || f.properties.WARD_NAME || `Ward ${wn}`;
            layer.bindTooltip(`<b>${name}</b><br>${METRICS[metric].label}: ${METRICS[metric].fmt(getVal(w, metric))}`, {
                className: 'ward-tooltip', sticky: true
            });
            layer.on('click', () => {
                showWardDetail(wn);
                showWard(wn);
            });
        }
    }).addTo(map);

    renderLegend(mn, mx, metric);
}

function getVal(w, m) {
    if (m === 'anomaly_score') return w.anomaly_score || 0;
    if (m === 'total_gross_lakhs') return w.total_gross_lakhs || 0;
    if (m === 'anomaly_count') return w.anomaly_count || 0;
    return w.total_orders || 0;
}

function getMetric() {
    const sel = document.getElementById('map-metric');
    return sel ? sel.value : 'anomaly_score';
}

function colorScale(v, mn, mx, pal) {
    const t = mx > mn ? (v - mn) / (mx - mn) : 0;
    if (t < 0.5) return lerpColor(pal[0], pal[1], t * 2);
    return lerpColor(pal[1], pal[2], (t - 0.5) * 2);
}

function lerpColor(a, b, t) {
    const pa = hexRGB(a), pb = hexRGB(b);
    const r = Math.round(pa[0] + (pb[0]-pa[0])*t);
    const g = Math.round(pa[1] + (pb[1]-pa[1])*t);
    const bl = Math.round(pa[2] + (pb[2]-pa[2])*t);
    return `rgb(${r},${g},${bl})`;
}

function hexRGB(h) {
    h = h.replace('#','');
    return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)];
}

function renderLegend(mn, mx, metric) {
    let el = document.getElementById('map-legend');
    if (!el) {
        el = document.createElement('div');
        el.id = 'map-legend';
        el.style.cssText = 'position:absolute;bottom:1.5rem;left:1.5rem;z-index:10;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:0.5rem 0.75rem;font-size:0.7rem;box-shadow:0 2px 8px rgba(0,0,0,0.08);';
        document.getElementById('map').parentElement.style.position = 'relative';
        document.getElementById('map').parentElement.appendChild(el);
    }
    const pal = METRICS[metric].palette;
    el.innerHTML = `
        <div style="font-weight:600;margin-bottom:0.25rem;color:var(--text-muted);">${METRICS[metric].label}</div>
        <div style="display:flex;align-items:center;gap:0.5rem;">
            <span style="color:var(--text-dim)">${METRICS[metric].fmt(mn)}</span>
            <div style="width:80px;height:8px;border-radius:4px;background:linear-gradient(to right,${pal[0]},${pal[1]},${pal[2]});"></div>
            <span style="color:var(--text-dim)">${METRICS[metric].fmt(mx)}</span>
        </div>`;
}

function showWardDetail(wardNo) {
    const panel = document.getElementById('ward-detail');
    if (!panel) return;
    const w = wardLookup[String(wardNo)];
    if (!w) {
        panel.innerHTML = '<div class="ward-detail-placeholder">No data for this ward</div>';
        return;
    }

    const cats = w.category_breakdown || {};
    const topCats = Object.entries(cats).sort((a,b) => b[1]-a[1]).slice(0, 6);
    const contractors = w.top_contractors || [];
    const anomalyTypes = Array.isArray(w.anomaly_types) ? w.anomaly_types : [];

    panel.innerHTML = `
        <div class="ward-detail-header">
            <h3>Ward ${wardNo} — ${esc(w.ward_name || '')}</h3>
            <div class="ward-zone">${esc(w.zone || '')} Zone</div>
        </div>
        <div class="ward-stats-grid">
            <div class="ward-mini-stat">
                <div class="ward-mini-stat-value">${fmt(w.total_orders)}</div>
                <div class="ward-mini-stat-label">Orders</div>
            </div>
            <div class="ward-mini-stat">
                <div class="ward-mini-stat-value">${fmtCr(w.total_gross_lakhs||0)}</div>
                <div class="ward-mini-stat-label">Spend</div>
            </div>
            <div class="ward-mini-stat">
                <div class="ward-mini-stat-value">${w.anomaly_count||0}</div>
                <div class="ward-mini-stat-label">Anomalies</div>
            </div>
            <div class="ward-mini-stat">
                <div class="ward-mini-stat-value">${(w.anomaly_score||0).toFixed(2)}</div>
                <div class="ward-mini-stat-label">Risk Score</div>
            </div>
        </div>
        <div class="ward-section">
            <h4>Top Categories</h4>
            ${topCats.map(([c,v]) => `
                <div class="ward-row"><span>${esc(c)}</span><span>${fmtL(v)}</span></div>
            `).join('')}
        </div>
        ${contractors.length ? `
        <div class="ward-section">
            <h4>Top Contractors</h4>
            ${contractors.slice(0,5).map(c => `
                <div class="ward-row"><span>${esc(c.name)}</span><span>${fmtL(c.value_lakhs)}</span></div>
            `).join('')}
        </div>` : ''}
        ${anomalyTypes.length ? `
        <div class="ward-section">
            <h4>Anomaly Types</h4>
            ${anomalyTypes.map(t => `
                <div class="ward-row"><span>${esc(t.replace(/_/g,' '))}</span></div>
            `).join('')}
        </div>` : ''}`;
}

function wireControls() {
    const sel = document.getElementById('map-metric');
    if (sel) sel.addEventListener('change', () => {
        if (geoLayer) { map.removeLayer(geoLayer); geoLayer = null; }
        loadGeo();
    });

    const search = document.getElementById('ward-search');
    if (search) search.addEventListener('input', () => {
        const q = search.value.trim().toLowerCase();
        if (!q) return;
        const match = Object.entries(wardLookup).find(([k, v]) =>
            k === q || (v.ward_name || '').toLowerCase().includes(q)
        );
        if (match) showWardDetail(match[0]);
    });
}

function refreshMap() {
    if (map) map.invalidateSize();
}

/* =====================================================================
   dashboard.js — Corruption-forward narrative dashboard
   ===================================================================== */

function initDashboard() {
    renderAlertBanner();
    renderScorecard();
    renderOffenders();
    renderPatternGrid();
    renderTenderZoneGaps();
    renderZoneBars();
}

/* ── Alert Banner ──────────────────────────────────────── */
function renderAlertBanner() {
    const el = document.getElementById('alert-banner');
    if (!el) return;
    const m = DATA.meta || {};
    const s = DATA.summary || {};
    const crit = m.critical_anomalies || 0;
    const high = m.high_anomalies || 0;

    // Count high-risk contractors
    const highRiskCon = (Array.isArray(DATA.contractors) ? DATA.contractors : [])
        .filter(c => (c.risk_score || 0) >= 0.6).length;

    // Count flagged wards (>5 anomalies)
    const flaggedWards = Object.values(DATA.wards || {})
        .filter(w => (w.anomaly_count || 0) > 5).length;

    el.innerHTML = `
    <div class="alert-banner">
        <div class="alert-banner-icon">🚨</div>
        <div class="alert-banner-text">
            Analysis found <strong>${crit.toLocaleString()} critical</strong> and
            <span class="hl-high">${high.toLocaleString()} high-severity</span> anomalies
            across <span class="hl-accent">${m.total_wards || 198} wards</span>.
            ${highRiskCon > 0 ? `<strong>${highRiskCon}</strong> contractors flagged as high-risk.` : ''}
            ${flaggedWards > 0 ? `<span class="hl-high">${flaggedWards}</span> wards have 5+ anomalies.` : ''}
        </div>
    </div>`;
}

/* ── Scorecard ─────────────────────────────────────────── */
function renderScorecard() {
    const el = document.getElementById('scorecard');
    if (!el) return;
    const m = DATA.meta || {};
    const s = DATA.summary || {};
    const crit = m.critical_anomalies || 0;
    const high = m.high_anomalies || 0;

    const highRiskCon = (Array.isArray(DATA.contractors) ? DATA.contractors : [])
        .filter(c => (c.risk_score || 0) >= 0.6).length;

    const flaggedWards = Object.values(DATA.wards || {})
        .filter(w => (w.anomaly_count || 0) > 5).length;

    el.innerHTML = `
        <div class="score-item">
            <div class="score-value">${fmtCr(s.total_gross_lakhs || 0)}</div>
            <div class="score-label">Total Spend</div>
            <div class="score-sub">${fmt(m.total_records)} orders</div>
        </div>
        <div class="score-item danger">
            <div class="score-value">${fmt(m.total_anomalies)}</div>
            <div class="score-label">Anomalies Found</div>
            <div class="score-sub">${crit} critical</div>
        </div>
        <div class="score-item danger">
            <div class="score-value">${(crit + high).toLocaleString()}</div>
            <div class="score-label">Critical + High</div>
            <div class="score-sub">${((crit + high) / Math.max(m.total_anomalies, 1) * 100).toFixed(0)}% of all</div>
        </div>
        <div class="score-item warn">
            <div class="score-value">${highRiskCon}</div>
            <div class="score-label">High-Risk Contractors</div>
            <div class="score-sub">risk score ≥ 0.6</div>
        </div>
        <div class="score-item warn">
            <div class="score-value">${flaggedWards}</div>
            <div class="score-label">Suspicious Wards</div>
            <div class="score-sub">&gt;5 anomalies each</div>
        </div>`;
}

/* ── Worst Offenders ───────────────────────────────────── */
function renderOffenders() {
    const el = document.getElementById('offenders-grid');
    if (!el) return;

    // Panel 1: Most suspicious contractors (by risk_score)
    const contractors = (Array.isArray(DATA.contractors) ? DATA.contractors : [])
        .filter(c => c.risk_score > 0)
        .sort((a, b) => b.risk_score - a.risk_score)
        .slice(0, 8);

    // Panel 2: Most flagged wards (by anomaly_count)
    const wards = Object.entries(DATA._wardIndex || {})
        .map(([k, v]) => ({ num: k, ...v }))
        .filter(w => w.anomaly_count > 0)
        .sort((a, b) => (b.anomaly_count || 0) - (a.anomaly_count || 0))
        .slice(0, 8);

    // Panel 3: Top critical anomalies
    const anomalies = (Array.isArray(DATA.anomalies) ? DATA.anomalies : [])
        .filter(a => a.severity === 'critical')
        .slice(0, 8);

    el.innerHTML = `
    <div class="offenders-panel">
        <div class="offenders-panel-header">
            <h3>🏢 Riskiest Contractors</h3>
            <span class="offenders-panel-count">by risk score</span>
        </div>
        ${contractors.map((c, i) => {
            const riskClass = c.risk_score >= 0.6 ? 'risk-crit' : c.risk_score >= 0.3 ? 'risk-high' : 'risk-med';
            return `<div class="offender-item" onclick="showContractor('${esc(c.contractor)}')">
                <span class="offender-rank">${i + 1}</span>
                <div class="offender-info">
                    <div class="offender-name">${esc(truncate(c.contractor, 32))}</div>
                    <div class="offender-meta">
                        <span>₹${fmtL(c.gross_lakhs || 0)}</span>
                        <span>${c.orders || 0} orders</span>
                        <span>${c.wards || 0} wards</span>
                    </div>
                </div>
                <div class="offender-badge">
                    <span class="risk-badge ${riskClass}">${(c.risk_score || 0).toFixed(2)}</span>
                </div>
            </div>`;
        }).join('')}
    </div>

    <div class="offenders-panel">
        <div class="offenders-panel-header">
            <h3>🚩 Most Flagged Wards</h3>
            <span class="offenders-panel-count">by anomaly count</span>
        </div>
        ${wards.map((w, i) => `
            <div class="offender-item" onclick="showWard('${w.num}')">
                <span class="offender-rank">${i + 1}</span>
                <div class="offender-info">
                    <div class="offender-name">${esc(w.ward_name || 'Ward ' + w.num)}</div>
                    <div class="offender-meta">
                        <span>₹${fmtCr(w.total_gross_lakhs || 0)}</span>
                        <span>${w.total_orders || 0} orders</span>
                    </div>
                </div>
                <div class="offender-badge">
                    <span class="value" style="color:var(--critical)">${w.anomaly_count || 0}</span>
                </div>
            </div>
        `).join('')}
    </div>

    <div class="offenders-panel">
        <div class="offenders-panel-header">
            <h3>🔥 Top Critical Flags</h3>
            <span class="offenders-panel-count">highest score</span>
        </div>
        ${anomalies.map((a, i) => {
            const meta = TYPE_META[a.type] || { icon: '❓', color: '#5a6178', label: a.type };
            return `<div class="offender-item" onclick="switchTab('investigate')">
                <span class="offender-rank">${i + 1}</span>
                <div class="offender-info">
                    <div class="offender-name" style="color:${meta.color}">${meta.icon} ${esc(truncate(a.description, 50))}</div>
                    <div class="offender-meta">
                        ${a.ward_name ? `<span>📍 ${esc(a.ward_name)}</span>` : ''}
                        <span>${meta.label}</span>
                    </div>
                </div>
                <div class="offender-badge">
                    <span class="risk-badge risk-crit">${(a.score || 0).toFixed(2)}</span>
                </div>
            </div>`;
        }).join('')}
    </div>`;
}

/* ── Pattern Detection Grid ────────────────────────────── */
function renderPatternGrid() {
    const el = document.getElementById('pattern-grid');
    if (!el) return;
    const typeIndex = DATA._typeIndex || {};
    const anomalies = Array.isArray(DATA.anomalies) ? DATA.anomalies : [];

    const types = Object.entries(typeIndex)
        .filter(([, v]) => v.total > 0)
        .sort((a, b) => b[1].total - a[1].total);

    el.innerHTML = types.map(([type, data]) => {
        const meta = TYPE_META[type] || { icon: '❓', color: '#5a6178', label: type };
        const worst = data.anomalies[0];
        return `
        <div class="pattern-card" onclick="filterByType('${type}')">
            <div class="pattern-card-header">
                <div class="pattern-icon" style="background:${meta.color}22">${meta.icon}</div>
                <div class="pattern-name">${meta.label}</div>
            </div>
            <div class="pattern-count">${data.total.toLocaleString()}</div>
            <div class="pattern-breakdown">
                ${data.critical > 0 ? `<span class="pattern-sev crit">${data.critical} crit</span>` : ''}
                ${data.high > 0 ? `<span class="pattern-sev high">${data.high} high</span>` : ''}
                ${data.medium > 0 ? `<span class="pattern-sev med">${data.medium} med</span>` : ''}
            </div>
            ${worst ? `<div class="pattern-example" title="${esc(worst.description)}">${esc(truncate(worst.description, 80))}</div>` : ''}
        </div>`;
    }).join('');
}

/* Click on pattern card -> go to investigate tab filtered */
function filterByType(type) {
    switchTab('investigate');
    if (typeof setTypeFilter === 'function') setTypeFilter(type);
}

/* ── Tender Zone Gap Analysis ──────────────────────────── */
function renderTenderZoneGaps() {
    const el = document.getElementById('tender-zone-bars');
    if (!el) return;
    const tenders = DATA.tenders || {};
    const zoneAnalysis = tenders.zone_analysis || {};
    const zones = Object.entries(zoneAnalysis).filter(([, v]) => v.gap_pct != null);
    if (!zones.length) { el.innerHTML = '<p style="color:var(--text-muted);text-align:center;">No tender data</p>'; return; }

    const summary = tenders.summary || {};
    const topOverruns = (tenders.top_overruns || []).slice(0, 5);

    zones.sort((a, b) => Math.abs(b[1].gap_pct) - Math.abs(a[1].gap_pct));
    const maxVal = Math.max(...zones.map(([, v]) => Math.max(v.tender_value_lakhs, v.actual_spend_lakhs)), 1);

    el.innerHTML = `
    <div class="tender-summary" style="display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:1rem;padding:0.5rem 0;">
        <div style="font-size:0.78rem;color:var(--text-secondary);">
            <strong>${fmt(summary.total_tenders)}</strong> tenders (2013–18) · <strong>₹${fmtCr(summary.total_value_lakhs || 0)}</strong> estimated
        </div>
    </div>
    <div class="zone-list">
    ${zones.map(([zone, d]) => {
        const estPct = (d.tender_value_lakhs / maxVal * 100).toFixed(1);
        const actPct = (d.actual_spend_lakhs / maxVal * 100).toFixed(1);
        const gap = d.gap_pct;
        const gapColor = gap > 50 ? 'var(--critical)' : gap > 20 ? 'var(--high)' : gap < -20 ? '#06b6d4' : 'var(--text-secondary)';
        const gapLabel = gap > 0 ? `+${gap}%` : `${gap}%`;
        const gapNote = gap > 50 ? 'Actual ≫ Estimated' : gap < -30 ? 'Underspent' : '';
        return `
        <div class="zone-row" style="margin-bottom:0.5rem;">
            <div class="zone-name" style="min-width:110px;">${esc(zone)}</div>
            <div style="flex:1;display:flex;flex-direction:column;gap:2px;">
                <div class="zone-bar-track" style="height:12px;">
                    <div class="zone-bar-fill" style="width:${estPct}%;background:#3b82f6;height:100%;border-radius:3px;position:relative;">
                        <span class="zone-bar-label" style="font-size:0.62rem;">Est ₹${fmtCr(d.tender_value_lakhs)}</span>
                    </div>
                </div>
                <div class="zone-bar-track" style="height:12px;">
                    <div class="zone-bar-fill" style="width:${actPct}%;background:${gap > 30 ? '#ef4444' : '#22c55e'};height:100%;border-radius:3px;position:relative;">
                        <span class="zone-bar-label" style="font-size:0.62rem;">Act ₹${fmtCr(d.actual_spend_lakhs)}</span>
                    </div>
                </div>
            </div>
            <div style="min-width:80px;text-align:right;">
                <span style="font-weight:700;color:${gapColor};font-size:0.82rem;font-family:var(--font-mono);">${gapLabel}</span>
                ${gapNote ? `<div style="font-size:0.6rem;color:${gapColor};">${gapNote}</div>` : ''}
            </div>
        </div>`;
    }).join('')}
    </div>
    ${topOverruns.length ? `
    <div style="margin-top:1rem;padding-top:0.75rem;border-top:1px solid var(--border);">
        <div style="font-size:0.72rem;font-weight:600;color:var(--text-secondary);margin-bottom:0.5rem;">🔴 Top Ward-Level Cost Overruns</div>
        ${topOverruns.map(g => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:0.25rem 0;font-size:0.75rem;cursor:pointer;" onclick="showWard('${g.ward}')">
                <span style="color:var(--text-primary);">Ward ${g.ward} — ${esc(g.ward_name)} <span style="color:var(--text-dim);">(${g.fy})</span></span>
                <span style="font-family:var(--font-mono);color:var(--critical);font-weight:700;">+${g.gap_pct > 9999 ? '9999' : g.gap_pct}% · ₹${fmtL(g.gap_lakhs)} gap</span>
            </div>
        `).join('')}
    </div>` : ''}`;
}

/* ── Zone Comparison Bars ──────────────────────────────── */
function renderZoneBars() {
    const el = document.getElementById('zone-bars');
    if (!el) return;
    const zones = Array.isArray(DATA.zones) ? DATA.zones : [];
    if (!zones.length) { el.innerHTML = '<p style="color:var(--text-muted);text-align:center;">No zone data</p>'; return; }

    const maxSpend = Math.max(...zones.map(z => z.total_gross_lakhs || 0), 1);
    const maxAnom = Math.max(...zones.map(z => z.total_anomalies || 0), 1);

    el.innerHTML = `<div class="zone-list">${zones.map(z => {
        const spendPct = ((z.total_gross_lakhs || 0) / maxSpend * 100).toFixed(1);
        const anomPct = ((z.total_anomalies || 0) / maxAnom * 100).toFixed(1);
        return `
        <div class="zone-row">
            <div class="zone-name">${esc(z.zone)}</div>
            <div class="zone-bar-track">
                <div class="zone-bar-fill spend" style="width:${spendPct}%">
                    <span class="zone-bar-label">${fmtCr(z.total_gross_lakhs || 0)}</span>
                </div>
            </div>
            <div class="zone-stats">${z.total_anomalies || 0} flags · ${z.ward_count || 0} wards</div>
        </div>`;
    }).join('')}</div>`;
}

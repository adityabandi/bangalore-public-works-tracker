/* =====================================================================
   stories.js — Investigation narratives for the editorial layout
   ===================================================================== */

function initStories() {
    renderHero();
    renderInvestigation1_KRIDL();
    renderInvestigation2_Tenders();
    renderInvestigation3_SplitOrders();
    renderInvestigation4_Payments();
    renderInvestigation5_RepeatWorks();
    renderByTheNumbers();

    // Ensure investigation cards become visible (fallback for IntersectionObserver)
    requestAnimationFrame(() => {
        document.querySelectorAll('.investigation').forEach((el, i) => {
            setTimeout(() => el.classList.add('visible'), i * 120);
        });
    });
}

/* ── Hero ──────────────────────────────────────────────── */
function renderHero() {
    const m = DATA.meta || {};
    const s = DATA.summary || {};
    const stories = DATA.stories || {};
    const ctx = stories.context || {};

    const totalCr = (s.total_gross_lakhs || 0) / 100;
    setText('hero-amount', '₹' + Math.round(totalCr).toLocaleString('en-IN') + ' Crores');
    setText('hero-anomaly-count', (m.total_anomalies || 0).toLocaleString('en-IN'));

    const crit = (m.critical_anomalies || 0) + (m.high_anomalies || 0);
    setText('hs-critical', crit.toLocaleString('en-IN'));
    setText('hs-orders', (m.total_records || 0).toLocaleString('en-IN'));
    setText('hs-wards', m.total_wards || 198);
    setText('hs-contractors', (m.total_contractors || 0).toLocaleString('en-IN'));
}

/* ── Investigation 1: The KRIDL Machine ───────────────── */
function renderInvestigation1_KRIDL() {
    const el = document.getElementById('inv-kridl');
    if (!el) return;
    const k = (DATA.stories || {}).kridl || {};
    if (!k.variant_count) { el.style.display = 'none'; return; }

    const variants = k.top_variants || [];
    const maxSpend = variants.length ? variants[0].spend_lakhs : 1;

    el.innerHTML = `
        <div class="inv-number">Investigation 01</div>
        <h2 class="inv-headline">One Government Entity. ${k.variant_count} Registered Names. ₹${k.total_spend_crores} Crores.</h2>
        <p class="inv-lede">
            KRIDL (Karnataka Rural Infrastructure Development Ltd) and its variants account for
            <strong>${k.pct_of_total}% of all BBMP public works spending</strong> — ₹${k.total_spend_crores} crores
            across ${k.total_orders.toLocaleString('en-IN')} work orders in ${k.wards_served} wards.
            The entity is registered under ${k.variant_count} different name variations, including names padded with
            zeros and garbage characters.
        </p>

        <div class="big-number-block">
            <div class="big-number">${k.pct_of_total}%</div>
            <div class="big-number-context">of all BBMP public works spending flows to a single entity operating under ${k.variant_count} different names</div>
        </div>

        <table class="evidence-table">
            <thead><tr>
                <th>Registered Name</th>
                <th class="num">Spend</th>
                <th class="num">Orders</th>
                <th style="width:200px;">Share</th>
            </tr></thead>
            <tbody>
            ${variants.slice(0, 15).map(v => `
                <tr>
                    <td class="name" style="cursor:pointer;color:var(--accent);" onclick="showContractor('${esc(v.name)}')">${esc(v.name)}</td>
                    <td class="num">₹${v.spend_crores} Cr</td>
                    <td class="num">${v.orders.toLocaleString('en-IN')}</td>
                    <td><div style="height:16px;background:var(--bg-elevated);border-radius:3px;overflow:hidden;"><div style="width:${(v.spend_lakhs/maxSpend*100).toFixed(1)}%;height:100%;background:var(--critical);border-radius:3px;"></div></div></td>
                </tr>
            `).join('')}
            </tbody>
        </table>

        <div class="evidence-callout">
            <div class="evidence-callout-title">Why this matters</div>
            <p>
                Name obfuscation — including entries like "KRIDL BHUSIRI ACCOU0000000000" with trailing zeros —
                makes it nearly impossible to track total spending to a single entity through standard audits.
                Whether intentional or a data-entry artifact, the result is the same: oversight is fragmented.
            </p>
        </div>`;
}

/* ── Investigation 2: Phantom Tenders ─────────────────── */
function renderInvestigation2_Tenders() {
    const el = document.getElementById('inv-tenders');
    if (!el) return;
    const t = (DATA.stories || {}).tender_gaps || {};
    const overruns = t.top_overruns || [];
    if (!overruns.length) { el.style.display = 'none'; return; }

    const worst = overruns[0];

    el.innerHTML = `
        <div class="inv-number">Investigation 02</div>
        <h2 class="inv-headline">Tendered at ₹${worst.tender_total_lakhs} Lakhs. Spent ₹${worst.actual_total_lakhs} Lakhs. A ${Math.round(worst.gap_pct).toLocaleString('en-IN')}% Gap.</h2>
        <p class="inv-lede">
            When BBMP publishes a tender, the estimated cost is meant to cap spending. But in ward after ward,
            actual expenditure dwarfs the original estimate — sometimes by orders of magnitude.
            In ${esc(worst.ward_name)}, the gap between tender and actual spend was
            <strong>${Math.round(worst.gap_pct).toLocaleString('en-IN')}%</strong>.
        </p>

        <div class="big-number-block">
            <div class="big-number">${Math.round(worst.gap_pct).toLocaleString('en-IN')}%</div>
            <div class="big-number-context">worst tender-to-actual cost gap — ${esc(worst.ward_name)} ward, FY ${worst.fy}</div>
        </div>

        <table class="evidence-table">
            <thead><tr>
                <th>Ward</th>
                <th>Zone</th>
                <th>FY</th>
                <th class="num">Tendered</th>
                <th class="num">Actual</th>
                <th class="num">Gap %</th>
                <th class="num">Gap Amount</th>
            </tr></thead>
            <tbody>
            ${overruns.slice(0, 10).map(g => `
                <tr class="${Math.abs(g.gap_pct) >= 1000 ? 'row-danger' : ''}">
                    <td style="cursor:pointer;color:var(--accent);" onclick="showWard('${g.ward}')">${esc(g.ward_name)}</td>
                    <td>${esc(g.zone)}</td>
                    <td>${g.fy}</td>
                    <td class="num">₹${Number(g.tender_total_lakhs).toFixed(1)}L</td>
                    <td class="num">₹${Number(g.actual_total_lakhs).toFixed(1)}L</td>
                    <td class="num danger">+${g.gap_pct > 9999 ? '9,999' : Math.round(g.gap_pct).toLocaleString('en-IN')}%</td>
                    <td class="num">₹${Number(g.gap_lakhs).toFixed(1)}L</td>
                </tr>
            `).join('')}
            </tbody>
        </table>

        <div class="evidence-callout">
            <div class="evidence-callout-title">Why this matters</div>
            <p>
                Tenders exist to ensure competitive pricing and prevent cost overruns.
                Gaps of 5,000–46,000% suggest either deliberate under-estimation to avoid scrutiny,
                or post-award scope changes without re-tendering — both red flags for procurement integrity.
            </p>
        </div>`;
}

/* ── Investigation 3: Split to Hide ───────────────────── */
function renderInvestigation3_SplitOrders() {
    const el = document.getElementById('inv-splits');
    if (!el) return;
    const s = (DATA.stories || {}).split_orders || {};
    const summary = DATA.summary || {};
    const anom = (summary.anomaly_summary || {}).split_order || {};

    const count = s.count || anom.count || 0;
    const critCount = s.critical_count || anom.critical || 0;
    if (!count) { el.style.display = 'none'; return; }

    const histogram = s.threshold_histogram || [];

    el.innerHTML = `
        <div class="inv-number">Investigation 03</div>
        <h2 class="inv-headline">${count} Orders Clustered Just Below Procurement Oversight Thresholds</h2>
        <p class="inv-lede">
            Government procurement rules require different levels of approval and competitive bidding
            above certain cost thresholds. Our analysis detected ${count} work orders
            (${critCount} critical) that cluster suspiciously just below these thresholds — a classic
            indicator of deliberate order-splitting to avoid oversight.
        </p>

        <div class="big-number-block">
            <div class="big-number">${count}</div>
            <div class="big-number-context">orders flagged for threshold-gaming — ${critCount} rated critical severity</div>
        </div>

        ${histogram.length ? `
        <div class="css-bar-chart">
            <p style="font-size:0.78rem;color:var(--text-muted);margin-bottom:1rem;font-weight:600;">Orders clustered just below each threshold:</p>
            ${histogram.filter(h => h.count > 0).map(h => {
                const maxCount = Math.max(...histogram.map(x => x.count), 1);
                const pct = (h.count / maxCount * 100).toFixed(1);
                return `<div class="css-bar-row">
                    <div class="css-bar-label">₹${h.threshold}</div>
                    <div class="css-bar-track">
                        <div class="css-bar-fill red" style="width:${pct}%">
                            <span class="css-bar-value">${h.count}</span>
                        </div>
                    </div>
                </div>`;
            }).join('')}
        </div>` : ''}

        <div class="evidence-callout">
            <div class="evidence-callout-title">Why this matters</div>
            <p>
                Splitting a single project into multiple smaller orders to stay below approval thresholds
                circumvents competitive bidding requirements. This means contracts can be awarded without
                open tenders, reducing transparency and enabling favoritism.
            </p>
        </div>`;
}

/* ── Investigation 4: Paid Before Built ───────────────── */
function renderInvestigation4_Payments() {
    const el = document.getElementById('inv-payments');
    if (!el) return;
    const p = (DATA.stories || {}).zero_day_payments || {};
    const summary = DATA.summary || {};
    const anom = (summary.anomaly_summary || {}).payment_speed || {};

    const count = p.count || anom.count || 0;
    if (!count) { el.style.display = 'none'; return; }

    const topWards = p.top_wards || [];
    const topContractors = p.top_contractors || [];

    el.innerHTML = `
        <div class="inv-number">Investigation 04</div>
        <h2 class="inv-headline">${count} Work Orders Paid on Day Zero. The Median Wait Is 676 Days.</h2>
        <p class="inv-lede">
            Across all BBMP work orders, the median time from approval to payment is 676 days.
            Yet ${count} orders were paid on the same day they were issued — all flagged as critical severity.
            Instant payment suggests pre-arranged deals where the outcome was determined before the process began.
        </p>

        <div class="big-number-block">
            <div class="big-number">0 days</div>
            <div class="big-number-context">${count} orders paid instantly — vs. a 676-day median across all orders</div>
        </div>

        ${topWards.length ? `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin:1.5rem 0;">
            <div>
                <p style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);margin-bottom:0.75rem;">Top Wards by Zero-Day Payments</p>
                ${topWards.slice(0, 8).map((w, i) => `
                    <div style="display:flex;justify-content:space-between;padding:0.3rem 0;font-size:0.82rem;border-bottom:1px solid var(--border-light);">
                        <span style="color:var(--text-secondary);">${i+1}. ${esc(w.name)}</span>
                        <span style="font-family:var(--font-mono);font-weight:600;color:var(--critical);">${w.count}</span>
                    </div>
                `).join('')}
            </div>
            ${topContractors.length ? `
            <div>
                <p style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);margin-bottom:0.75rem;">Top Contractors by Zero-Day Payments</p>
                ${topContractors.slice(0, 8).map((c, i) => `
                    <div style="display:flex;justify-content:space-between;padding:0.3rem 0;font-size:0.82rem;border-bottom:1px solid var(--border-light);">
                        <span style="color:var(--accent);cursor:pointer;" onclick="showContractor('${esc(c.name)}')">${i+1}. ${esc(truncate(c.name, 28))}</span>
                        <span style="font-family:var(--font-mono);font-weight:600;color:var(--critical);">${c.count}</span>
                    </div>
                `).join('')}
            </div>` : ''}
        </div>` : ''}

        <div class="evidence-callout">
            <div class="evidence-callout-title">Why this matters</div>
            <p>
                Standard payment processes include verification, quality checks, and multi-level approvals —
                none of which can happen in zero days. Immediate payment suggests the work was either
                pre-approved regardless of quality, or the payment system was manipulated.
            </p>
        </div>`;
}

/* ── Investigation 5: The Eternal Pothole ─────────────── */
function renderInvestigation5_RepeatWorks() {
    const el = document.getElementById('inv-repeats');
    if (!el) return;
    const r = (DATA.stories || {}).repeat_works || {};
    const cases = r.worst_cases || [];
    const totalClusters = r.total_clusters || 0;
    if (!totalClusters) { el.style.display = 'none'; return; }

    el.innerHTML = `
        <div class="inv-number">Investigation 05</div>
        <h2 class="inv-headline">Same Road. Same Budget. Year After Year. ${totalClusters} Locations.</h2>
        <p class="inv-lede">
            ${totalClusters} locations across Bangalore have received budget allocations for identical work
            across 3 or more fiscal years. Some locations show the same pothole-filling or road resurfacing
            work funded for 8 consecutive years — raising questions about whether the work is actually being
            completed, or whether budgets are being recycled through the same locations.
        </p>

        <div class="big-number-block">
            <div class="big-number">${totalClusters}</div>
            <div class="big-number-context">locations with repeat budget allocations for identical work across 3+ fiscal years</div>
        </div>

        ${cases.length ? `
        <table class="evidence-table">
            <thead><tr>
                <th>Ward</th>
                <th>Category</th>
                <th>Work Description</th>
                <th class="num">Years</th>
                <th class="num">Orders</th>
                <th class="num">Total Spend</th>
            </tr></thead>
            <tbody>
            ${cases.slice(0, 12).map(c => `
                <tr class="${c.fy_count >= 6 ? 'row-danger' : ''}">
                    <td style="cursor:pointer;color:var(--accent);" onclick="showWard('${c.ward}')">${esc(c.ward_name)}</td>
                    <td>${esc(c.category)}</td>
                    <td class="name" title="${esc(c.description_sample)}">${esc(truncate(c.description_sample, 50))}</td>
                    <td class="num" style="${c.fy_count >= 6 ? 'color:var(--critical);font-weight:700;' : ''}">${c.fy_count}</td>
                    <td class="num">${c.order_count}</td>
                    <td class="num">₹${Number(c.total_spend_lakhs).toFixed(1)}L</td>
                </tr>
            `).join('')}
            </tbody>
        </table>` : ''}

        <div class="evidence-callout">
            <div class="evidence-callout-title">Why this matters</div>
            <p>
                If a road is resurfaced in 2014, 2015, 2016, 2017, and 2018, either the construction quality
                is so poor it needs annual replacement, or the budgets are being allocated for work that
                never actually happens. Both scenarios represent a failure of public spending.
            </p>
        </div>`;
}

/* ── By The Numbers ───────────────────────────────────── */
function renderByTheNumbers() {
    const el = document.getElementById('stats-grid');
    if (!el) return;
    const m = DATA.meta || {};
    const s = DATA.summary || {};
    const ctx = (DATA.stories || {}).context || {};
    const totalCr = (s.total_gross_lakhs || 0) / 100;

    const stats = [
        { value: '₹' + Math.round(totalCr).toLocaleString('en-IN') + ' Cr', label: 'Total spending analyzed', red: false },
        { value: (m.total_anomalies || 0).toLocaleString('en-IN'), label: 'Anomalies flagged', red: true },
        { value: (m.total_records || 0).toLocaleString('en-IN'), label: 'Work orders processed', red: false },
        { value: ((m.critical_anomalies || 0) + (m.high_anomalies || 0)).toLocaleString('en-IN'), label: 'Critical + high severity', red: true },
        { value: (m.total_contractors || 0).toLocaleString('en-IN'), label: 'Unique contractors', red: false },
        { value: m.total_wards || 198, label: 'Wards covered', red: false },
        { value: '₹' + Math.round(ctx.per_resident || 0).toLocaleString('en-IN'), label: 'Per Bangalore resident', red: false },
        { value: '10', label: 'Detection algorithms', red: false },
    ];

    el.innerHTML = stats.map(s => `
        <div class="stat-block">
            <div class="stat-block-value ${s.red ? 'red' : ''}">${s.value}</div>
            <div class="stat-block-label">${s.label}</div>
        </div>
    `).join('');
}

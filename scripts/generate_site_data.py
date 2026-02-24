"""Generate compact JSON files for the static dashboard from processed data."""

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    PROJECT_ROOT, PROCESSED_DIR, SITE_DIR,
    ANOMALIES_FEED_LIMIT, CONTRACTORS_LIMIT, TOP_CONTRACTORS_PER_WARD,
    REPEAT_WORK_MIN_OCCURRENCES, REPEAT_WORK_SIMILARITY, REPEAT_WORK_MIN_AMOUNT,
    BID_BENCHMARK_FACTOR, BID_MIN_GROUP_SIZE, BID_MIN_AMOUNT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WARD_MAPPING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "benchmarks", "ward_mapping.json",
)


def load_data():
    """Load processed work orders and anomalies."""
    csv_path = os.path.join(PROCESSED_DIR, "all_work_orders.csv")
    if not os.path.exists(csv_path):
        logger.error(f"CSV not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, low_memory=False)
    logger.info(f"Loaded {len(df)} work orders")

    for col in ["gross", "deduction", "nett"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    anomalies_path = os.path.join(PROCESSED_DIR, "anomalies.json")
    anomalies = []
    if os.path.exists(anomalies_path):
        with open(anomalies_path) as f:
            anomalies = json.load(f)
        logger.info(f"Loaded {len(anomalies)} anomalies")

    return df, anomalies


def load_ward_mapping():
    """Load ward name and zone mapping from benchmarks/ward_mapping.json."""
    if not os.path.exists(WARD_MAPPING_PATH):
        logger.warning(f"Ward mapping not found: {WARD_MAPPING_PATH}")
        return {}, {}
    with open(WARD_MAPPING_PATH) as f:
        data = json.load(f)
    names = data.get("ward_198_to_name", {})
    zones = data.get("ward_198_to_zone", {})
    return names, zones


def _gross_lakhs(val):
    """Convert rupees to lakhs, rounded to 1dp."""
    try:
        return round(float(val) / 1e5, 1)
    except (TypeError, ValueError):
        return 0.0


def _fiscal_year(date_val):
    """Return 'YYYY-YY' fiscal year string from a date value."""
    try:
        dt = pd.to_datetime(date_val)
        if pd.isna(dt):
            return "unknown"
        if dt.month >= 4:
            return f"{dt.year}-{str(dt.year + 1)[2:]}"
        return f"{dt.year - 1}-{str(dt.year)[2:]}"
    except Exception:
        return "unknown"


def _norm_ward(w):
    """Normalize ward key: '1.0' → '1', '2' → '2'."""
    if w is None or w == "" or (isinstance(w, float) and pd.isna(w)):
        return ""
    w = str(w).strip()
    if not w or w.lower() in ("none", "nan"):
        return ""
    try:
        return str(int(float(w)))
    except (ValueError, TypeError):
        return w


# ── 1. meta.json ─────────────────────────────────────────────────────────────

def build_meta(df, anomalies):
    severities = [a.get("severity", "") for a in anomalies]
    critical = sum(1 for s in severities if s == "critical")
    high = sum(1 for s in severities if s == "high")

    contractors = df["contractor"].dropna().nunique() if "contractor" in df.columns else 0
    wards = df["ward_198"].dropna().nunique() if "ward_198" in df.columns else 0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(df),
        "total_anomalies": len(anomalies),
        "critical_anomalies": critical,
        "high_anomalies": high,
        "total_wards": int(wards),
        "total_contractors": int(contractors),
    }


# ── 2. summary.json ───────────────────────────────────────────────────────────

def build_summary(df, anomalies):
    total_gross = df["gross"].sum() if "gross" in df.columns else 0
    total_gross_lakhs = _gross_lakhs(total_gross)

    by_category = {}
    if "category" in df.columns and "gross" in df.columns:
        for cat, grp in df.groupby("category"):
            by_category[str(cat)] = _gross_lakhs(grp["gross"].sum())

    anomaly_summary = defaultdict(lambda: {"count": 0, "critical": 0, "high": 0, "medium": 0})
    for a in anomalies:
        atype = a.get("anomaly_type", a.get("type", "unknown"))
        sev = a.get("severity", "")
        anomaly_summary[atype]["count"] += 1
        if sev in ("critical", "high", "medium"):
            anomaly_summary[atype][sev] += 1

    return {
        "total_gross_lakhs": total_gross_lakhs,
        "by_category": by_category,
        "anomaly_summary": dict(anomaly_summary),
    }


# ── 3. timeseries.json ────────────────────────────────────────────────────────

def build_timeseries(df):
    if "order_date" not in df.columns and "start_date" not in df.columns:
        return {}

    date_col = "order_date" if "order_date" in df.columns else "start_date"
    df = df.copy()
    df["_fy"] = df[date_col].apply(_fiscal_year)

    result = {}
    for fy, grp in df.groupby("_fy"):
        if fy == "unknown" or str(fy).startswith("nan"):
            continue
        by_cat = {}
        if "category" in grp.columns:
            for cat, cgrp in grp.groupby("category"):
                by_cat[str(cat)] = _gross_lakhs(cgrp["gross"].sum()) if "gross" in cgrp.columns else 0
        result[str(fy)] = {
            "count": len(grp),
            "gross_lakhs": _gross_lakhs(grp["gross"].sum()) if "gross" in grp.columns else 0,
            "by_category": by_cat,
        }
    return result


# ── 4. wards.json ─────────────────────────────────────────────────────────────

def build_wards(df, anomalies, ward_names, ward_zones):
    if "ward_198" not in df.columns:
        logger.warning("ward_198 column missing — skipping wards.json")
        return {}

    # Anomaly counts and types per ward
    ward_anomaly_count = defaultdict(int)
    ward_anomaly_score = defaultdict(float)
    ward_anomaly_types = defaultdict(set)
    for a in anomalies:
        w = _norm_ward(a.get("ward_198", ""))
        if not w:
            continue
        ward_anomaly_count[w] += 1
        ward_anomaly_score[w] = max(ward_anomaly_score[w], a.get("score", 0))
        atype = a.get("anomaly_type", a.get("type", ""))
        if atype:
            ward_anomaly_types[w].add(atype)

    result = {}
    for ward_val, grp in df.groupby("ward_198"):
        if pd.isna(ward_val):
            continue
        w = _norm_ward(ward_val)

        name = ward_names.get(w, grp["ward_name"].iloc[0] if "ward_name" in grp.columns else f"Ward {w}")
        zone = ward_zones.get(w, "Unknown")

        by_cat = {}
        if "category" in grp.columns:
            for cat, cgrp in grp.groupby("category"):
                by_cat[str(cat)] = len(cgrp)

        top_contractors = []
        if "contractor" in grp.columns and "gross" in grp.columns:
            con_grp = grp.dropna(subset=["contractor"])
            con_stats = (
                con_grp.groupby("contractor")
                .agg(orders=("contractor", "count"), value=("gross", "sum"))
                .sort_values("value", ascending=False)
                .head(TOP_CONTRACTORS_PER_WARD)
            )
            for con, row in con_stats.iterrows():
                top_contractors.append({
                    "name": str(con),
                    "orders": int(row["orders"]),
                    "value_lakhs": _gross_lakhs(row["value"]),
                })

        result[w] = {
            "ward_name": str(name),
            "zone": str(zone),
            "total_orders": len(grp),
            "total_gross_lakhs": _gross_lakhs(grp["gross"].sum()) if "gross" in grp.columns else 0,
            "avg_order_lakhs": _gross_lakhs(grp["gross"].mean()) if "gross" in grp.columns else 0,
            "anomaly_count": ward_anomaly_count.get(w, 0),
            "anomaly_score": round(ward_anomaly_score.get(w, 0.0), 3),
            "category_breakdown": by_cat,
            "top_contractors": top_contractors,
            "anomaly_types": sorted(ward_anomaly_types.get(w, set())),
        }

    return result


# ── 5. anomalies.json (feed) ──────────────────────────────────────────────────

def build_anomalies_feed(anomalies):
    feed = []
    sorted_anomalies = sorted(anomalies, key=lambda a: a.get("score", 0), reverse=True)
    for a in sorted_anomalies[:ANOMALIES_FEED_LIMIT]:
        feed.append({
            "id": a.get("anomaly_id", a.get("id", "")),
            "type": a.get("anomaly_type", a.get("type", "")),
            "severity": a.get("severity", ""),
            "score": round(float(a.get("score", 0)), 3),
            "ward_number": _norm_ward(a.get("ward_198", "")),
            "ward_name": str(a.get("ward_name", "")),
            "category": str(a.get("category", "")),
            "description": str(a.get("description", "")),
        })
    return feed


# ── 6. contractors.json ───────────────────────────────────────────────────────

def build_contractors(df, anomalies=None, repeat_works=None, bids=None):
    if "contractor" not in df.columns:
        return []

    anomalies = anomalies or []
    repeat_works = repeat_works or []
    bids = bids or {}

    # Pre-compute anomaly counts per contractor (from description field)
    con_anomaly_counts = defaultdict(int)
    for a in anomalies:
        desc = str(a.get("description", ""))
        # Anomalies often mention the contractor name in the description
        details = a.get("details", {}) if isinstance(a.get("details"), dict) else {}
        con_name = details.get("contractor", "") or ""
        if con_name:
            con_anomaly_counts[con_name] += 1

    # Pre-compute repeat work involvement per contractor
    con_repeat_counts = defaultdict(int)
    for rw in repeat_works:
        for c in (rw.get("contractors") or []):
            con_repeat_counts[c["name"]] += 1

    # Pre-compute bid outlier counts per contractor
    con_bid_outlier_counts = defaultdict(int)
    for o in (bids.get("outlier_orders") or []):
        cname = o.get("contractor", "")
        if cname:
            con_bid_outlier_counts[cname] += 1

    rows = []
    con_df = df.dropna(subset=["contractor"])
    for con, grp in con_df.groupby("contractor"):
        con_str = str(con)
        wards = grp["ward_198"].dropna().nunique() if "ward_198" in grp.columns else 0
        orders = len(grp)

        # Top categories by spend
        top_cats = []
        if "category" in grp.columns and "gross" in grp.columns:
            cat_spend = grp.groupby("category")["gross"].sum().sort_values(ascending=False)
            top_cats = cat_spend.head(3).index.tolist()

        # Top wards by spend
        top_wards = []
        if "ward_198" in grp.columns and "gross" in grp.columns:
            ward_spend = grp.groupby("ward_198")["gross"].sum().sort_values(ascending=False)
            top_wards = [_norm_ward(w) for w in ward_spend.head(3).index.tolist()]

        anom_count = con_anomaly_counts.get(con_str, 0)
        repeat_count = con_repeat_counts.get(con_str, 0)
        bid_outlier_count = con_bid_outlier_counts.get(con_str, 0)

        # Risk score: 0-1 composite
        # Components: anomaly density, repeat involvement, bid overpricing
        anomaly_density = min(anom_count / max(orders, 1), 1.0)     # 0-1
        repeat_score = min(repeat_count / 5.0, 1.0)                  # 5+ clusters = max
        bid_score = min(bid_outlier_count / 3.0, 1.0)                # 3+ outliers = max
        risk_score = round(
            0.4 * anomaly_density + 0.35 * repeat_score + 0.25 * bid_score,
            3,
        )

        rows.append({
            "contractor": con_str,
            "gross_lakhs": _gross_lakhs(grp["gross"].sum()) if "gross" in grp.columns else 0,
            "orders": orders,
            "wards": int(wards),
            "anomaly_count": anom_count,
            "repeat_work_count": repeat_count,
            "bid_outlier_count": bid_outlier_count,
            "risk_score": risk_score,
            "top_categories": top_cats,
            "top_wards": top_wards,
        })

    rows.sort(key=lambda r: r["gross_lakhs"], reverse=True)
    return rows[:CONTRACTORS_LIMIT]


# ── 7. zones.json ─────────────────────────────────────────────────────────────

def build_zones(df, anomalies, ward_zones):
    if "ward_198" not in df.columns:
        return []

    # Map ward → zone in dataframe
    df = df.copy()
    df["_zone"] = df["ward_198"].apply(
        lambda w: ward_zones.get(str(int(w)) if pd.notna(w) and float(w) == int(float(w)) else str(w), "Unknown")
        if pd.notna(w) else "Unknown"
    )

    # Anomaly counts per ward
    ward_anomaly_count = defaultdict(int)
    for a in anomalies:
        w = _norm_ward(a.get("ward_198", ""))
        if w:
            ward_anomaly_count[w] += 1

    result = []
    for zone, grp in df.groupby("_zone"):
        ward_nums = set()
        for w in grp["ward_198"].dropna():
            try:
                ward_nums.add(str(int(w)))
            except (ValueError, TypeError):
                ward_nums.add(str(w))

        total_anomalies = sum(ward_anomaly_count.get(w, 0) for w in ward_nums)
        result.append({
            "zone": str(zone),
            "ward_count": grp["ward_198"].nunique(),
            "total_orders": len(grp),
            "total_gross_lakhs": _gross_lakhs(grp["gross"].sum()) if "gross" in grp.columns else 0,
            "total_anomalies": total_anomalies,
        })

    result.sort(key=lambda r: r["total_gross_lakhs"], reverse=True)
    return result


# ── 8. insights.json ──────────────────────────────────────────────────────────

def build_insights(df, anomalies, ward_names):
    insights = []

    # 1. Largest single order
    if "gross" in df.columns and "name_of_work" in df.columns:
        idx = df["gross"].idxmax()
        if pd.notna(idx):
            row = df.loc[idx]
            ward_w = str(int(row["ward_198"])) if "ward_198" in df.columns and pd.notna(row.get("ward_198")) else ""
            wname = ward_names.get(ward_w, row.get("ward_name", ""))
            insights.append({
                "type": "largest_order",
                "label": "Largest Single Order",
                "value": f"Rs {_gross_lakhs(row['gross']):.1f}L",
                "detail": f"{str(row.get('name_of_work', ''))[:80]} — {wname}",
            })

    # 2. Top contractor by spend
    if "contractor" in df.columns and "gross" in df.columns:
        con_totals = df.dropna(subset=["contractor"]).groupby("contractor")["gross"].sum()
        if not con_totals.empty:
            top_con = con_totals.idxmax()
            insights.append({
                "type": "top_contractor",
                "label": "Top Contractor by Spend",
                "value": f"Rs {_gross_lakhs(con_totals[top_con]):.1f}L",
                "detail": str(top_con),
            })

    # 3. Most flagged ward
    if anomalies and "ward_198" in df.columns:
        ward_counts = defaultdict(int)
        for a in anomalies:
            w = _norm_ward(a.get("ward_198", ""))
            if w:
                ward_counts[w] += 1
        if ward_counts:
            top_ward = max(ward_counts, key=ward_counts.get)
            wname = ward_names.get(top_ward, f"Ward {top_ward}")
            insights.append({
                "type": "most_flagged_ward",
                "label": "Most Flagged Ward",
                "value": f"{ward_counts[top_ward]} anomalies",
                "detail": wname,
            })

    # 4. Highest spend ward
    if "ward_198" in df.columns and "gross" in df.columns:
        ward_spend = df.dropna(subset=["ward_198"]).groupby("ward_198")["gross"].sum()
        if not ward_spend.empty:
            top_w = ward_spend.idxmax()
            wkey = str(int(top_w)) if float(top_w) == int(float(top_w)) else str(top_w)
            wname = ward_names.get(wkey, f"Ward {wkey}")
            insights.append({
                "type": "highest_spend_ward",
                "label": "Highest Spend Ward",
                "value": f"Rs {_gross_lakhs(ward_spend[top_w]):.1f}L",
                "detail": wname,
            })

    # 5. Largest category by spend
    if "category" in df.columns and "gross" in df.columns:
        cat_spend = df.dropna(subset=["category"]).groupby("category")["gross"].sum()
        if not cat_spend.empty:
            top_cat = cat_spend.idxmax()
            insights.append({
                "type": "largest_category",
                "label": "Largest Spending Category",
                "value": f"Rs {_gross_lakhs(cat_spend[top_cat]):.1f}L",
                "detail": str(top_cat).capitalize(),
            })

    # 6. Duplicate value anomalies
    dup_count = sum(
        1 for a in anomalies
        if a.get("anomaly_type", a.get("type", "")) in ("duplicate_work", "split_order")
    )
    if dup_count > 0:
        insights.append({
            "type": "duplicate_value",
            "label": "Duplicate / Split Orders",
            "value": f"{dup_count} flagged",
            "detail": "Orders with similar descriptions or suspicious amount splits",
        })

    return insights[:6]


# ── 9. repeat_works.json ──────────────────────────────────────────────────────

def _extract_tokens(text):
    import re
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    stops = {"of", "the", "and", "in", "to", "at", "for", "a", "an",
             "no", "sl", "ward", "work", "from", "with", "by", "on"}
    return set(w for w in text.split() if w and w not in stops and len(w) > 1)


def _jaccard(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def build_repeat_works(df, ward_names):
    """Build repeat works data — locations budgeted year after year."""
    result = []

    if "fiscal_year" not in df.columns or "name_of_work" not in df.columns:
        logger.warning("Repeat works: missing fiscal_year or name_of_work columns")
        return result

    df_valid = df.dropna(subset=["ward_198", "name_of_work", "fiscal_year"]).copy()
    df_valid = df_valid[df_valid["gross"] >= REPEAT_WORK_MIN_AMOUNT]
    df_valid = df_valid[df_valid["fiscal_year"].str.strip() != ""]

    for (ward, cat), group in df_valid.groupby(["ward_198", "category"]):
        if pd.isna(ward) or len(group) < REPEAT_WORK_MIN_OCCURRENCES:
            continue

        records = group.to_dict("records")
        tokens = [_extract_tokens(r.get("name_of_work", "")) for r in records]
        used = set()
        clusters = []

        for i in range(len(records)):
            if i in used:
                continue
            cluster = [i]
            used.add(i)
            for j in range(i + 1, len(records)):
                if j in used:
                    continue
                if _jaccard(tokens[i], tokens[j]) >= REPEAT_WORK_SIMILARITY:
                    cluster.append(j)
                    used.add(j)
            clusters.append(cluster)

        for indices in clusters:
            if len(indices) < REPEAT_WORK_MIN_OCCURRENCES:
                continue
            cluster_recs = [records[i] for i in indices]
            fiscal_years = sorted(set(
                r.get("fiscal_year", "") for r in cluster_recs
                if r.get("fiscal_year", "").strip()
            ))
            if len(fiscal_years) < REPEAT_WORK_MIN_OCCURRENCES:
                continue

            total_spend = sum(r.get("gross", 0) or 0 for r in cluster_recs)
            w = _norm_ward(ward)
            wname = ward_names.get(w, cluster_recs[0].get("ward_name", f"Ward {w}"))

            # ── Contractor analysis for this cluster ──
            con_spend = defaultdict(lambda: {"orders": 0, "spend": 0})
            for r in cluster_recs:
                cname = str(r.get("contractor", "") or "").strip()
                if cname:
                    con_spend[cname]["orders"] += 1
                    con_spend[cname]["spend"] += r.get("gross", 0) or 0

            # Top 5 contractors by spend
            con_list = sorted(con_spend.items(), key=lambda x: x[1]["spend"], reverse=True)[:5]
            contractors = [
                {"name": c, "orders": d["orders"], "spend_lakhs": _gross_lakhs(d["spend"])}
                for c, d in con_list
            ]

            # Dominance: % of orders going to #1 contractor
            total_orders_with_con = sum(d["orders"] for d in con_spend.values())
            top_con_orders = con_list[0][1]["orders"] if con_list else 0
            same_contractor_pct = round(
                top_con_orders / total_orders_with_con * 100, 1
            ) if total_orders_with_con > 0 else 0.0
            dominant = con_list[0][0] if con_list and same_contractor_pct >= 50 else None

            result.append({
                "ward": w,
                "ward_name": str(wname),
                "category": str(cat),
                "fiscal_years": fiscal_years,
                "fy_count": len(fiscal_years),
                "order_count": len(cluster_recs),
                "total_spend_lakhs": _gross_lakhs(total_spend),
                "avg_order_lakhs": _gross_lakhs(total_spend / len(cluster_recs)) if cluster_recs else 0,
                "description_sample": str(cluster_recs[0].get("name_of_work", ""))[:100],
                "contractors": contractors,
                "same_contractor_pct": same_contractor_pct,
                "dominant_contractor": dominant,
            })

    result.sort(key=lambda r: r["fy_count"], reverse=True)
    logger.info(f"Repeat works: {len(result)} clusters")
    return result


# ── 10. bids.json ─────────────────────────────────────────────────────────────

def _load_sor():
    sor_path = os.path.join(PROJECT_ROOT, "benchmarks", "karnataka_sor_2024.json")
    if not os.path.exists(sor_path):
        return {}
    with open(sor_path) as f:
        data = json.load(f)
    return data.get("rates", {})


def build_bids(df):
    """Build bid analysis data — compare work order costs to SoR benchmarks."""
    sor = _load_sor()
    if not sor:
        logger.warning("Bids: no SoR benchmarks")
        return {"categories": [], "outlier_orders": [], "contractor_pricing": []}

    # Average SoR rate per category
    cat_sor_avg = {}
    for cat, items in sor.items():
        rates = [v["rate_inr"] for v in items.values() if "rate_inr" in v]
        if rates:
            cat_sor_avg[cat] = round(sum(rates) / len(rates), 0)

    df_valid = df.dropna(subset=["ward_198", "gross", "category"]).copy()
    df_valid = df_valid[df_valid["gross"] >= BID_MIN_AMOUNT]

    # Category summary
    categories = []
    for cat in cat_sor_avg:
        cat_df = df_valid[df_valid["category"] == cat]
        if cat_df.empty:
            continue
        categories.append({
            "category": cat,
            "sor_avg_rate": cat_sor_avg[cat],
            "median_order_lakhs": _gross_lakhs(cat_df["gross"].median()),
            "mean_order_lakhs": _gross_lakhs(cat_df["gross"].mean()),
            "max_order_lakhs": _gross_lakhs(cat_df["gross"].max()),
            "order_count": len(cat_df),
        })

    # Outlier orders (above benchmark threshold per ward-category)
    outlier_orders = []
    for (ward, cat), group in df_valid.groupby(["ward_198", "category"]):
        if pd.isna(ward) or len(group) < BID_MIN_GROUP_SIZE:
            continue
        if cat not in cat_sor_avg:
            continue

        median_cost = group["gross"].median()
        threshold = median_cost * BID_BENCHMARK_FACTOR
        outliers = group[group["gross"] > threshold]

        for _, row in outliers.iterrows():
            ratio = row["gross"] / median_cost if median_cost > 0 else 1
            outlier_orders.append({
                "ward": _norm_ward(ward),
                "ward_name": str(row.get("ward_name", "")),
                "category": str(cat),
                "amount_lakhs": _gross_lakhs(row["gross"]),
                "ward_median_lakhs": _gross_lakhs(median_cost),
                "ratio": round(ratio, 2),
                "contractor": str(row.get("contractor", "")),
            })

    outlier_orders.sort(key=lambda r: r["ratio"], reverse=True)

    # Contractor pricing (avg price per contractor per category vs ward median)
    contractor_pricing = []
    if "contractor" in df_valid.columns:
        for (con, cat), group in df_valid.groupby(["contractor", "category"]):
            if pd.isna(con) or cat not in cat_sor_avg or len(group) < 3:
                continue
            cat_median = df_valid[df_valid["category"] == cat]["gross"].median()
            con_avg = group["gross"].mean()
            ratio = con_avg / cat_median if cat_median > 0 else 1
            contractor_pricing.append({
                "contractor": str(con),
                "category": str(cat),
                "avg_order_lakhs": _gross_lakhs(con_avg),
                "category_median_lakhs": _gross_lakhs(cat_median),
                "ratio": round(ratio, 2),
                "order_count": len(group),
                "total_lakhs": _gross_lakhs(group["gross"].sum()),
            })

    contractor_pricing.sort(key=lambda r: r["ratio"], reverse=True)

    logger.info(f"Bids: {len(categories)} categories, {len(outlier_orders)} outliers, {len(contractor_pricing)} contractor entries")
    return {
        "categories": categories,
        "outlier_orders": outlier_orders,
        "contractor_pricing": contractor_pricing,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def save_json(data, filename):
    os.makedirs(SITE_DIR, exist_ok=True)
    path = os.path.join(SITE_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"), default=str)
    logger.info(f"Saved {filename} ({os.path.getsize(path):,} bytes)")


def main():
    df, anomalies = load_data()
    ward_names, ward_zones = load_ward_mapping()

    save_json(build_meta(df, anomalies), "meta.json")
    save_json(build_summary(df, anomalies), "summary.json")
    save_json(build_timeseries(df), "timeseries.json")
    save_json(build_wards(df, anomalies, ward_names, ward_zones), "wards.json")
    save_json(build_anomalies_feed(anomalies), "anomalies.json")
    save_json(build_zones(df, anomalies, ward_zones), "zones.json")
    save_json(build_insights(df, anomalies, ward_names), "insights.json")

    # Build repeat_works and bids first, so contractors can cross-reference them
    repeat_works_data = build_repeat_works(df, ward_names)
    bids_data = build_bids(df)
    save_json(repeat_works_data, "repeat_works.json")
    save_json(bids_data, "bids.json")

    # Contractors with risk profile (cross-references anomalies, repeat works, bid outliers)
    save_json(build_contractors(df, anomalies, repeat_works_data, bids_data), "contractors.json")

    logger.info("All 10 site JSON files generated.")


if __name__ == "__main__":
    main()

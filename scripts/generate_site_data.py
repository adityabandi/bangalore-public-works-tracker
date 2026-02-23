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
    PROCESSED_DIR, SITE_DIR,
    ANOMALIES_FEED_LIMIT, CONTRACTORS_LIMIT, TOP_CONTRACTORS_PER_WARD,
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
        if dt.month >= 4:
            return f"{dt.year}-{str(dt.year + 1)[2:]}"
        return f"{dt.year - 1}-{str(dt.year)[2:]}"
    except Exception:
        return "unknown"


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
        if fy == "unknown":
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
        w = str(a.get("ward_198", "")).strip()
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
        w = str(int(ward_val)) if float(ward_val) == int(float(ward_val)) else str(ward_val)

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
            "ward_number": str(a.get("ward_198", "")),
            "ward_name": str(a.get("ward_name", "")),
            "category": str(a.get("category", "")),
            "description": str(a.get("description", "")),
        })
    return feed


# ── 6. contractors.json ───────────────────────────────────────────────────────

def build_contractors(df):
    if "contractor" not in df.columns:
        return []

    rows = []
    con_df = df.dropna(subset=["contractor"])
    for con, grp in con_df.groupby("contractor"):
        wards = grp["ward_198"].dropna().nunique() if "ward_198" in grp.columns else 0
        rows.append({
            "contractor": str(con),
            "gross_lakhs": _gross_lakhs(grp["gross"].sum()) if "gross" in grp.columns else 0,
            "orders": len(grp),
            "wards": int(wards),
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
        w = str(a.get("ward_198", "")).strip()
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
            w = str(a.get("ward_198", "")).strip()
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
    save_json(build_contractors(df), "contractors.json")
    save_json(build_zones(df, anomalies, ward_zones), "zones.json")
    save_json(build_insights(df, anomalies, ward_names), "insights.json")

    logger.info("All 8 site JSON files generated.")


if __name__ == "__main__":
    main()

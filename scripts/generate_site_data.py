"""Generate compact JSON files for the static dashboard from processed data."""

import hashlib
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    PROCESSED_DIR, SITE_DIR,
    ANOMALIES_FEED_LIMIT, CONTRACTORS_LIMIT, TOP_CONTRACTORS_PER_WARD,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_data():
    """Load processed work orders and anomalies."""
    csv_path = os.path.join(PROCESSED_DIR, "all_work_orders.csv")
    anomalies_path = os.path.join(PROCESSED_DIR, "anomalies.json")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Run normalize.py first: {csv_path}")
    if not os.path.exists(anomalies_path):
        raise FileNotFoundError(f"Run detect_anomalies.py first: {anomalies_path}")

    df = pd.read_csv(csv_path, low_memory=False)
    date_cols = ["start_date", "end_date", "order_date", "payment_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    with open(anomalies_path) as f:
        anomalies = json.load(f)

    return df, anomalies


def generate_meta(df: pd.DataFrame, anomalies: list) -> dict:
    """Dashboard metadata."""
    min_date = df["order_date"].min()
    max_date = df["order_date"].max()
    return {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_records": len(df),
        "date_range": {
            "start": min_date.isoformat()[:10] if pd.notna(min_date) else None,
            "end": max_date.isoformat()[:10] if pd.notna(max_date) else None,
        },
        "anomalies_detected": len(anomalies),
        "total_spend_crores": round(df["gross"].sum() / 1e7, 2),
        "categories": sorted(df["category"].unique().tolist()),
        "fiscal_years": sorted(
            [fy for fy in df["fiscal_year"].unique() if isinstance(fy, str) and fy],
            reverse=True
        ),
    }


def generate_summary(df: pd.DataFrame, anomalies: list) -> dict:
    """City-wide aggregate statistics."""
    by_category = {}
    for cat, grp in df.groupby("category"):
        by_category[cat] = {
            "count": len(grp),
            "gross_lakhs": round(grp["gross"].sum() / 1e5, 1),
            "pct": round(len(grp) / len(df) * 100, 1),
        }

    by_fy = {}
    for fy, grp in df.groupby("fiscal_year"):
        if not fy:
            continue
        by_fy[fy] = {
            "count": len(grp),
            "gross_lakhs": round(grp["gross"].sum() / 1e5, 1),
        }

    # Anomaly type summary
    anomaly_types = defaultdict(lambda: {"count": 0, "critical": 0, "high": 0})
    for a in anomalies:
        t = a["anomaly_type"]
        anomaly_types[t]["count"] += 1
        label = a.get("severity_label", "low")
        if label in ("critical", "high"):
            anomaly_types[t][label] += 1

    return {
        "total_gross_lakhs": round(df["gross"].sum() / 1e5, 1),
        "total_net_lakhs": round(df["nett"].sum() / 1e5, 1),
        "total_records": len(df),
        "by_category": by_category,
        "by_fiscal_year": dict(sorted(by_fy.items(), reverse=True)),
        "anomaly_summary": dict(anomaly_types),
    }


def generate_wards(df: pd.DataFrame, anomalies: list) -> dict:
    """Per-ward aggregate data for the map."""
    # Index anomalies by ward
    anomaly_by_ward = defaultdict(list)
    for a in anomalies:
        w = a.get("ward_198")
        if w is not None:
            anomaly_by_ward[w].append(a)

    wards = {}
    for ward, grp in df.groupby("ward_198"):
        if pd.isna(ward):
            continue
        ward_key = str(int(ward))
        ward_anomalies = anomaly_by_ward.get(int(ward), [])

        # Ward name
        ward_name = ""
        if "ward_name" in grp.columns:
            names = grp["ward_name"].dropna()
            if len(names) > 0:
                mode = names.mode()
                ward_name = mode.iloc[0] if len(mode) > 0 else ""

        # Zone
        zone = ""
        if "zone" in grp.columns:
            zones = grp["zone"].dropna()
            if len(zones) > 0:
                mode = zones.mode()
                zone = mode.iloc[0] if len(mode) > 0 else ""

        # Top contractors
        top = (
            grp[grp["contractor"].str.len() > 0]
            .groupby("contractor")
            .agg(orders=("id", "size"), value=("gross", "sum"))
            .sort_values("value", ascending=False)
            .head(TOP_CONTRACTORS_PER_WARD)
        )
        top_contractors = [
            {
                "name": name,
                "orders": int(row["orders"]),
                "value_lakhs": round(row["value"] / 1e5, 1),
            }
            for name, row in top.iterrows()
        ]

        # Category breakdown
        by_cat = grp["category"].value_counts().to_dict()

        # Anomaly score: average severity of ward anomalies
        avg_severity = 0
        if ward_anomalies:
            avg_severity = sum(a["severity"] for a in ward_anomalies) / len(ward_anomalies)

        wards[ward_key] = {
            "name": ward_name or f"Ward {ward_key}",
            "zone": zone,
            "total_orders": len(grp),
            "total_gross_lakhs": round(grp["gross"].sum() / 1e5, 1),
            "by_category": by_cat,
            "anomaly_count": len(ward_anomalies),
            "anomaly_score": round(avg_severity, 3),
            "top_contractors": top_contractors,
        }

    return wards


def generate_anomaly_feed(anomalies: list) -> list:
    """Top anomalies sorted by severity for the feed."""
    sorted_a = sorted(anomalies, key=lambda a: a["severity"], reverse=True)
    feed = []
    for a in sorted_a[:ANOMALIES_FEED_LIMIT]:
        feed.append({
            "id": hashlib.sha256(
                json.dumps(a, sort_keys=True, default=str).encode()
            ).hexdigest()[:12],
            "type": a["anomaly_type"],
            "severity": a["severity"],
            "severity_label": a.get("severity_label", "low"),
            "description": a["description"],
            "ward_198": a.get("ward_198"),
            "ward_name": a.get("ward_name", ""),
            "contractor": a.get("contractor", ""),
            "fiscal_year": a.get("fiscal_year", ""),
        })
    return feed


def generate_contractors(df: pd.DataFrame, anomalies: list) -> dict:
    """Contractor profiles with concentration and anomaly data."""
    df_valid = df[df["contractor"].str.len() > 0]

    # Index anomalies by contractor
    anomaly_by_contractor = defaultdict(list)
    for a in anomalies:
        c = a.get("contractor", "")
        if c:
            anomaly_by_contractor[c].append(a)

    contractor_stats = (
        df_valid.groupby("contractor")
        .agg(
            total_orders=("id", "size"),
            total_gross=("gross", "sum"),
            wards=("ward_198", lambda x: sorted(x.dropna().unique().tolist())),
            categories=("category", lambda x: x.value_counts().to_dict()),
            fiscal_years=("fiscal_year", lambda x: sorted(x[x != ""].unique().tolist())),
        )
        .sort_values("total_gross", ascending=False)
        .head(CONTRACTORS_LIMIT)
    )

    contractors = {}
    for name, row in contractor_stats.iterrows():
        c_anomalies = anomaly_by_contractor.get(name, [])
        contractors[name] = {
            "name": name,
            "total_orders": int(row["total_orders"]),
            "total_gross_lakhs": round(row["total_gross"] / 1e5, 1),
            "wards_active": [int(w) for w in row["wards"] if pd.notna(w)][:20],
            "categories": row["categories"],
            "fiscal_years": row["fiscal_years"],
            "anomaly_count": len(c_anomalies),
        }

    return contractors


def generate_timeseries(df: pd.DataFrame) -> dict:
    """Monthly and yearly spending time series."""
    yearly = {}
    for fy, grp in df.groupby("fiscal_year"):
        if not fy:
            continue
        by_cat = {}
        for cat, cat_grp in grp.groupby("category"):
            by_cat[cat] = round(cat_grp["gross"].sum() / 1e5, 1)
        yearly[fy] = {
            "total_lakhs": round(grp["gross"].sum() / 1e5, 1),
            "count": len(grp),
            "by_category": by_cat,
        }

    return {"yearly": dict(sorted(yearly.items()))}


def write_json(data, filename: str):
    """Write JSON file to site directory."""
    path = os.path.join(SITE_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=None, default=str)
    size_kb = os.path.getsize(path) / 1024
    logger.info(f"  {filename}: {size_kb:.1f} KB")


def main():
    """Generate all site JSON files."""
    df, anomalies = load_data()
    logger.info(f"Loaded {len(df)} work orders, {len(anomalies)} anomalies")

    os.makedirs(SITE_DIR, exist_ok=True)

    logger.info("Generating site data:")
    write_json(generate_meta(df, anomalies), "meta.json")
    write_json(generate_summary(df, anomalies), "summary.json")
    write_json(generate_wards(df, anomalies), "wards.json")
    write_json(generate_anomaly_feed(anomalies), "anomalies.json")
    write_json(generate_contractors(df, anomalies), "contractors.json")
    write_json(generate_timeseries(df), "timeseries.json")

    logger.info("Site data generation complete")


if __name__ == "__main__":
    main()

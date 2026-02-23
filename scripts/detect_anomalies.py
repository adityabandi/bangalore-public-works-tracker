"""Anomaly detection engine: 6 heuristics for flagging suspicious BBMP work orders."""

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
    COST_OUTLIER_IQR_FACTOR, COST_OUTLIER_MIN_AMOUNT, COST_OUTLIER_MIN_GROUP_SIZE,
    CONTRACTOR_WARD_THRESHOLD, CONTRACTOR_CITY_THRESHOLD, CONTRACTOR_MIN_ORDERS,
    DUPLICATE_SIMILARITY_THRESHOLD, DUPLICATE_TIME_WINDOW_DAYS,
    PAYMENT_SPEED_PERCENTILE, PAYMENT_SPEED_MIN_GROUP,
    DEDUCTION_IQR_FACTOR, DEDUCTION_MIN_GROUP,
    BENFORD_CHI_SQUARED_THRESHOLD, BENFORD_MIN_SAMPLE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Benford's Law expected first-digit frequencies
BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046,
}


def detect_cost_outliers(df: pd.DataFrame) -> list[dict]:
    """Flag projects significantly above ward/category averages using IQR."""
    anomalies = []
    mask = df["gross"] >= COST_OUTLIER_MIN_AMOUNT
    analysis = df[mask].copy()

    for (ward, category), group in analysis.groupby(["ward_198", "category"]):
        if pd.isna(ward) or len(group) < COST_OUTLIER_MIN_GROUP_SIZE:
            continue

        q1 = group["gross"].quantile(0.25)
        q3 = group["gross"].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue

        upper = q3 + COST_OUTLIER_IQR_FACTOR * iqr
        median = group["gross"].median()
        mean = group["gross"].mean()
        std = group["gross"].std()

        outliers = group[group["gross"] > upper]
        for _, row in outliers.iterrows():
            z_score = (row["gross"] - mean) / std if std > 0 else 0
            severity = min(1.0, (row["gross"] - upper) / (upper - median)) if upper > median else 0.5

            ward_name = row.get("ward_name", "") or ""
            work_desc = str(row.get("name_of_work", ""))[:80]

            anomalies.append({
                "work_order_id": row.get("id", ""),
                "anomaly_type": "cost_outlier",
                "severity": round(max(0, severity), 3),
                "description": (
                    f"{work_desc} in Ward {int(ward)} ({ward_name}) "
                    f"at Rs {row['gross']:,.0f} is {row['gross'] / median:.1f}x the median "
                    f"for {category} works in this ward"
                ),
                "details": {
                    "amount": float(row["gross"]),
                    "ward_category_median": float(median),
                    "z_score": round(z_score, 2),
                    "iqr_factor": round((row["gross"] - q3) / iqr, 2),
                    "group_size": len(group),
                },
                "ward_198": int(ward),
                "ward_name": ward_name,
                "contractor": row.get("contractor", ""),
                "fiscal_year": row.get("fiscal_year", ""),
            })

    logger.info(f"Cost outliers: {len(anomalies)} detected")
    return anomalies


def detect_contractor_concentration(df: pd.DataFrame) -> list[dict]:
    """Flag contractors winning disproportionate share of work orders."""
    anomalies = []
    df_valid = df[df["contractor"].str.len() > 0].copy()

    # Ward-level concentration
    ward_totals = df_valid.groupby("ward_198").size()
    ward_contractor = (
        df_valid.groupby(["ward_198", "contractor"])
        .agg(count=("id", "size"), total_value=("gross", "sum"))
        .reset_index()
    )
    ward_contractor["ward_total"] = ward_contractor["ward_198"].map(ward_totals)
    ward_contractor["share_pct"] = (
        ward_contractor["count"] / ward_contractor["ward_total"]
    )

    flagged = ward_contractor[
        (ward_contractor["share_pct"] > CONTRACTOR_WARD_THRESHOLD)
        & (ward_contractor["count"] >= CONTRACTOR_MIN_ORDERS)
    ]

    for _, row in flagged.iterrows():
        if pd.isna(row["ward_198"]):
            continue
        severity = min(1.0, (row["share_pct"] - CONTRACTOR_WARD_THRESHOLD) / 0.35)
        ward_num = int(row["ward_198"])

        # Look up ward name
        ward_records = df_valid[df_valid["ward_198"] == ward_num]
        ward_name = ""
        if "ward_name" in ward_records.columns:
            names = ward_records["ward_name"].dropna()
            if len(names) > 0:
                ward_name = names.mode().iloc[0] if len(names.mode()) > 0 else ""

        anomalies.append({
            "anomaly_type": "contractor_concentration",
            "severity": round(max(0, severity), 3),
            "description": (
                f"{row['contractor']} has {row['share_pct'] * 100:.1f}% of orders "
                f"in Ward {ward_num} ({ward_name}) "
                f"({int(row['count'])} of {int(row['ward_total'])} orders, "
                f"Rs {row['total_value']:,.0f} total)"
            ),
            "details": {
                "contractor_name": row["contractor"],
                "ward_share_pct": round(row["share_pct"] * 100, 1),
                "total_orders": int(row["count"]),
                "total_value": float(row["total_value"]),
            },
            "ward_198": ward_num,
            "ward_name": ward_name,
            "contractor": row["contractor"],
            "fiscal_year": "",
        })

    # City-level concentration
    city_total = len(df_valid)
    city_contractor = (
        df_valid.groupby("contractor")
        .agg(count=("id", "size"), total_value=("gross", "sum"))
        .reset_index()
    )
    city_contractor["share_pct"] = city_contractor["count"] / city_total

    city_flagged = city_contractor[
        (city_contractor["share_pct"] > CONTRACTOR_CITY_THRESHOLD)
        & (city_contractor["count"] >= CONTRACTOR_MIN_ORDERS)
    ]

    for _, row in city_flagged.iterrows():
        severity = min(1.0, (row["share_pct"] - CONTRACTOR_CITY_THRESHOLD) / 0.10)
        anomalies.append({
            "anomaly_type": "contractor_concentration",
            "severity": round(max(0, severity), 3),
            "description": (
                f"{row['contractor']} has {row['share_pct'] * 100:.1f}% of ALL city-wide orders "
                f"({int(row['count'])} of {city_total}, Rs {row['total_value']:,.0f} total)"
            ),
            "details": {
                "contractor_name": row["contractor"],
                "city_share_pct": round(row["share_pct"] * 100, 1),
                "total_orders": int(row["count"]),
                "total_value": float(row["total_value"]),
            },
            "ward_198": None,
            "ward_name": "",
            "contractor": row["contractor"],
            "fiscal_year": "",
        })

    logger.info(f"Contractor concentration: {len(anomalies)} detected")
    return anomalies


def detect_duplicate_works(df: pd.DataFrame) -> list[dict]:
    """Flag near-identical work descriptions in same ward within 12 months."""
    anomalies = []
    seen_pairs = set()

    for (ward, category), group in df.groupby(["ward_198", "category"]):
        if pd.isna(ward) or len(group) < 2:
            continue

        group = group.sort_values("order_date")
        records = group.to_dict("records")

        for i in range(len(records)):
            desc_i = str(records[i].get("name_of_work", "")).lower().split()
            date_i = records[i].get("order_date")
            set_i = set(desc_i) if desc_i else set()
            if len(set_i) < 3:
                continue

            for j in range(i + 1, min(i + 50, len(records))):  # Cap comparisons
                date_j = records[j].get("order_date")

                # Time window check
                gap = None
                if pd.notna(date_i) and pd.notna(date_j):
                    gap = (date_j - date_i).days
                    if gap > DUPLICATE_TIME_WINDOW_DAYS:
                        break

                desc_j = str(records[j].get("name_of_work", "")).lower().split()
                set_j = set(desc_j) if desc_j else set()
                if len(set_j) < 3:
                    continue

                # Jaccard similarity
                intersection = len(set_i & set_j)
                union = len(set_i | set_j)
                if union == 0:
                    continue
                similarity = intersection / union

                if similarity >= DUPLICATE_SIMILARITY_THRESHOLD:
                    id_i = records[i].get("id", "")
                    id_j = records[j].get("id", "")
                    pair_key = tuple(sorted([id_i, id_j]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    ward_name = records[i].get("ward_name", "") or ""
                    work_i = str(records[i].get("name_of_work", ""))[:60]
                    work_j = str(records[j].get("name_of_work", ""))[:60]
                    gap_str = f", {gap} days apart" if gap is not None else ""

                    anomalies.append({
                        "work_order_id": id_i,
                        "anomaly_type": "duplicate_work",
                        "severity": round(similarity, 3),
                        "description": (
                            f"Similar works in Ward {int(ward)} ({ward_name}): "
                            f"'{work_i}' and '{work_j}'{gap_str}"
                        ),
                        "details": {
                            "similar_work_ids": [id_i, id_j],
                            "similarity_score": round(similarity, 3),
                            "time_gap_days": gap,
                        },
                        "ward_198": int(ward),
                        "ward_name": ward_name,
                        "contractor": records[i].get("contractor", ""),
                        "fiscal_year": records[i].get("fiscal_year", ""),
                    })

    logger.info(f"Duplicate works: {len(anomalies)} detected")
    return anomalies


def detect_payment_speed(df: pd.DataFrame) -> list[dict]:
    """Flag suspiciously fast payments (order to payment)."""
    anomalies = []

    mask = df["order_date"].notna() & df["payment_date"].notna()
    analysis = df[mask].copy()
    analysis["payment_days"] = (analysis["payment_date"] - analysis["order_date"]).dt.days

    # Filter to reasonable range
    analysis = analysis[(analysis["payment_days"] >= 0) & (analysis["payment_days"] <= 3650)]

    for category, group in analysis.groupby("category"):
        if len(group) < PAYMENT_SPEED_MIN_GROUP:
            continue

        threshold = group["payment_days"].quantile(PAYMENT_SPEED_PERCENTILE / 100)
        median_days = group["payment_days"].median()

        fast = group[group["payment_days"] <= max(threshold, 3)]
        for _, row in fast.iterrows():
            if median_days > 0:
                severity = max(0, 1.0 - (row["payment_days"] / median_days))
            else:
                severity = 0.5

            ward_name = row.get("ward_name", "") or ""
            work_desc = str(row.get("name_of_work", ""))[:60]

            anomalies.append({
                "work_order_id": row.get("id", ""),
                "anomaly_type": "payment_speed",
                "severity": round(min(1.0, severity), 3),
                "description": (
                    f"Payment in {int(row['payment_days'])} days for '{work_desc}' "
                    f"(category median: {median_days:.0f} days)"
                ),
                "details": {
                    "order_to_payment_days": int(row["payment_days"]),
                    "median_days_for_category": round(median_days, 1),
                },
                "ward_198": int(row["ward_198"]) if pd.notna(row.get("ward_198")) else None,
                "ward_name": ward_name,
                "contractor": row.get("contractor", ""),
                "fiscal_year": row.get("fiscal_year", ""),
            })

    logger.info(f"Payment speed anomalies: {len(anomalies)} detected")
    return anomalies


def detect_deduction_ratio(df: pd.DataFrame) -> list[dict]:
    """Flag unusual gross-to-net deduction ratios."""
    anomalies = []

    mask = df["gross"] > 0
    analysis = df[mask].copy()
    analysis["deduction_pct"] = (analysis["deduction"] / analysis["gross"]) * 100

    for category, group in analysis.groupby("category"):
        if len(group) < DEDUCTION_MIN_GROUP:
            continue

        q1 = group["deduction_pct"].quantile(0.25)
        q3 = group["deduction_pct"].quantile(0.75)
        iqr = q3 - q1
        median_pct = group["deduction_pct"].median()

        if iqr == 0:
            continue

        lower = q1 - DEDUCTION_IQR_FACTOR * iqr
        upper = q3 + DEDUCTION_IQR_FACTOR * iqr

        outliers = group[(group["deduction_pct"] < lower) | (group["deduction_pct"] > upper)]
        for _, row in outliers.iterrows():
            direction = "low" if row["deduction_pct"] < lower else "high"
            severity = abs(row["deduction_pct"] - median_pct) / (iqr * 5) if iqr > 0 else 0.5
            severity = min(1.0, severity)

            ward_name = row.get("ward_name", "") or ""

            anomalies.append({
                "work_order_id": row.get("id", ""),
                "anomaly_type": "deduction_ratio",
                "severity": round(max(0, severity), 3),
                "description": (
                    f"Unusually {direction} deduction ({row['deduction_pct']:.1f}%) "
                    f"vs median {median_pct:.1f}% for {category} works"
                ),
                "details": {
                    "gross": float(row["gross"]),
                    "deduction": float(row["deduction"]),
                    "deduction_pct": round(row["deduction_pct"], 2),
                    "median_deduction_pct": round(median_pct, 2),
                },
                "ward_198": int(row["ward_198"]) if pd.notna(row.get("ward_198")) else None,
                "ward_name": ward_name,
                "contractor": row.get("contractor", ""),
                "fiscal_year": row.get("fiscal_year", ""),
            })

    logger.info(f"Deduction ratio anomalies: {len(anomalies)} detected")
    return anomalies


def detect_benford_violations(df: pd.DataFrame) -> list[dict]:
    """Chi-squared test on first-digit distribution of spending amounts per ward."""
    anomalies = []

    for ward, group in df.groupby("ward_198"):
        if pd.isna(ward):
            continue
        amounts = group["gross"][group["gross"] > 0]
        if len(amounts) < BENFORD_MIN_SAMPLE:
            continue

        first_digits = amounts.apply(lambda x: int(str(int(abs(x)))[0]))
        observed = first_digits.value_counts(normalize=True)

        chi_sq = 0
        digit_details = {}
        for digit in range(1, 10):
            obs = observed.get(digit, 0)
            exp = BENFORD_EXPECTED[digit]
            chi_sq += ((obs - exp) ** 2) / exp
            digit_details[str(digit)] = {
                "observed": round(obs, 4),
                "expected": round(exp, 4),
            }

        if chi_sq > BENFORD_CHI_SQUARED_THRESHOLD:
            severity = min(1.0, (chi_sq - BENFORD_CHI_SQUARED_THRESHOLD) / 30)

            ward_name = ""
            names = group["ward_name"].dropna()
            if len(names) > 0:
                mode = names.mode()
                ward_name = mode.iloc[0] if len(mode) > 0 else ""

            anomalies.append({
                "anomaly_type": "benford_violation",
                "severity": round(severity, 3),
                "description": (
                    f"Ward {int(ward)} ({ward_name}) spending fails Benford's Law test "
                    f"(chi-squared: {chi_sq:.1f}, threshold: {BENFORD_CHI_SQUARED_THRESHOLD})"
                ),
                "details": {
                    "chi_squared": round(chi_sq, 2),
                    "sample_size": len(amounts),
                    "digit_distribution": digit_details,
                },
                "ward_198": int(ward),
                "ward_name": ward_name,
                "contractor": "",
                "fiscal_year": "",
            })

    logger.info(f"Benford violations: {len(anomalies)} detected")
    return anomalies


def run_all_detectors(df: pd.DataFrame) -> list[dict]:
    """Run all anomaly detection heuristics."""
    all_anomalies = []

    detectors = [
        ("cost_outlier", detect_cost_outliers),
        ("contractor_concentration", detect_contractor_concentration),
        ("duplicate_work", detect_duplicate_works),
        ("payment_speed", detect_payment_speed),
        ("deduction_ratio", detect_deduction_ratio),
        ("benford_violation", detect_benford_violations),
    ]

    for name, detector in detectors:
        try:
            results = detector(df)
            all_anomalies.extend(results)
        except Exception as e:
            logger.error(f"Detector {name} failed: {e}", exc_info=True)

    # Assign severity labels and timestamps
    for a in all_anomalies:
        s = a["severity"]
        if s >= 0.8:
            a["severity_label"] = "critical"
        elif s >= 0.6:
            a["severity_label"] = "high"
        elif s >= 0.4:
            a["severity_label"] = "medium"
        else:
            a["severity_label"] = "low"
        a["detected_at"] = datetime.utcnow().isoformat() + "Z"

    logger.info(f"Total anomalies detected: {len(all_anomalies)}")
    return all_anomalies


def main():
    """Load processed data and run anomaly detection."""
    csv_path = os.path.join(PROCESSED_DIR, "all_work_orders.csv")
    if not os.path.exists(csv_path):
        logger.error(f"Processed data not found: {csv_path}")
        logger.error("Run normalize.py first")
        return

    logger.info(f"Loading data from {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)

    # Re-parse dates that were serialized as strings
    date_cols = ["start_date", "end_date", "order_date", "payment_date",
                 "sbr_date", "br_date", "cbr_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    anomalies = run_all_detectors(df)

    # Save anomalies
    os.makedirs(SITE_DIR, exist_ok=True)
    out_path = os.path.join(PROCESSED_DIR, "anomalies.json")
    with open(out_path, "w") as f:
        json.dump(anomalies, f, indent=None, default=str)
    logger.info(f"Saved {len(anomalies)} anomalies to {out_path}")


if __name__ == "__main__":
    main()

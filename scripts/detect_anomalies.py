"""Anomaly detection engine - 10 heuristics for flagging suspicious BBMP work orders."""

import hashlib
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    PROJECT_ROOT,
    PROCESSED_DIR,
    COST_OUTLIER_IQR_FACTOR,
    COST_OUTLIER_MIN_AMOUNT,
    COST_OUTLIER_MIN_GROUP_SIZE,
    CONTRACTOR_WARD_THRESHOLD,
    CONTRACTOR_CITY_THRESHOLD,
    CONTRACTOR_MIN_ORDERS,
    DUPLICATE_SIMILARITY_THRESHOLD,
    DUPLICATE_TIME_WINDOW_DAYS,
    PAYMENT_SPEED_PERCENTILE,
    PAYMENT_SPEED_MIN_GROUP,
    DEDUCTION_IQR_FACTOR,
    DEDUCTION_MIN_GROUP,
    BENFORD_CHI_SQUARED_THRESHOLD,
    BENFORD_MIN_SAMPLE,
    REPEAT_WORK_MIN_OCCURRENCES,
    REPEAT_WORK_SIMILARITY,
    REPEAT_WORK_MIN_AMOUNT,
    BID_BENCHMARK_FACTOR,
    BID_MIN_GROUP_SIZE,
    BID_MIN_AMOUNT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SPLIT_ORDER_THRESHOLDS = [500_000, 1_000_000, 2_500_000, 5_000_000,
                          10_000_000, 25_000_000, 50_000_000]
SPLIT_BAND_PCT = 0.15


def _ward_label(ward_num, ward_name):
    name = str(ward_name or "").strip()
    num = str(ward_num or "").strip()
    if name and num:
        return f"Ward {num} ({name})"
    return f"Ward {num}" if num else "Unknown ward"


def _severity(score):
    if score >= 0.75:
        return "critical"
    if score >= 0.50:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def _anomaly_id(parts):
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _extract_tokens(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    stops = {"of", "the", "and", "in", "to", "at", "for", "a", "an",
             "no", "sl", "ward", "work", "from", "with", "by", "on"}
    return [w for w in text.split() if w and w not in stops and len(w) > 1]


def _jaccard(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


# Detector 1: Cost Outliers

def detect_cost_outliers(df):
    anomalies = []
    df_valid = df.dropna(subset=["gross"]).copy()
    df_valid = df_valid[df_valid["gross"] >= COST_OUTLIER_MIN_AMOUNT]

    for (ward, cat), group in df_valid.groupby(["ward_198", "category"]):
        if pd.isna(ward) or len(group) < COST_OUTLIER_MIN_GROUP_SIZE:
            continue
        q1 = group["gross"].quantile(0.25)
        q3 = group["gross"].quantile(0.75)
        iqr = q3 - q1
        if iqr < 1:
            continue
        upper = q3 + COST_OUTLIER_IQR_FACTOR * iqr
        outliers = group[group["gross"] > upper]
        for _, row in outliers.iterrows():
            ratio = row["gross"] / upper if upper > 0 else 1
            score = min(1.0, 0.4 + 0.2 * ratio)
            ward_name = row.get("ward_name", "")
            anomalies.append({
                "anomaly_id": _anomaly_id(["cost", ward, cat, row["gross"]]),
                "anomaly_type": "cost_outlier",
                "severity": _severity(score),
                "score": round(score, 3),
                "ward_198": str(ward),
                "ward_name": ward_name,
                "category": cat,
                "description": (
                    f"Rs {row['gross']/1e5:,.1f}L {cat} order in {_ward_label(ward, ward_name)} "
                    f"is {ratio:.1f}x above the IQR threshold of Rs {upper/1e5:,.1f}L"
                ),
                "details": {
                    "amount": float(row["gross"]),
                    "threshold": round(upper, 0),
                    "ratio": round(ratio, 2),
                    "group_median": round(group["gross"].median(), 0),
                    "group_size": len(group),
                },
            })
    logger.info(f"Cost outliers: {len(anomalies)} flagged")
    return anomalies


# Detector 2: Contractor Concentration

def detect_contractor_concentration(df):
    anomalies = []
    df_valid = df.dropna(subset=["contractor", "ward_198"]).copy()
    df_valid = df_valid[df_valid["contractor"].str.strip() != ""]

    ward_counts = df_valid.groupby("ward_198").size()
    ward_contractor = (
        df_valid.groupby(["ward_198", "contractor"])
        .agg(count=("gross", "size"), total=("gross", "sum"))
        .reset_index()
    )

    for _, row in ward_contractor.iterrows():
        ward = row["ward_198"]
        total_ward = ward_counts.get(ward, 0)
        if total_ward < CONTRACTOR_MIN_ORDERS:
            continue
        share = row["count"] / total_ward
        if share < CONTRACTOR_WARD_THRESHOLD:
            continue
        names = df_valid[df_valid["ward_198"] == ward]["ward_name"].dropna()
        ward_name = names.iloc[0] if len(names) > 0 else ""
        score = min(1.0, share * 1.5)
        anomalies.append({
            "anomaly_id": _anomaly_id(["conc_ward", ward, row["contractor"]]),
            "anomaly_type": "contractor_concentration",
            "severity": _severity(score),
            "score": round(score, 3),
            "ward_198": str(ward),
            "ward_name": ward_name,
            "category": "",
            "description": (
                f"{row['contractor']} holds {share:.0%} of orders "
                f"({row['count']}/{total_ward}) in {_ward_label(ward, ward_name)} "
                f"totalling Rs {row['total']/1e5:,.0f}L"
            ),
            "details": {
                "contractor": row["contractor"],
                "orders": int(row["count"]),
                "ward_total_orders": int(total_ward),
                "share": round(share, 3),
                "value": float(row["total"]),
            },
        })

    city_total = len(df_valid)
    city_contractor = (
        df_valid.groupby("contractor")
        .agg(count=("gross", "size"), total=("gross", "sum"))
        .reset_index()
    )
    for _, row in city_contractor.iterrows():
        share = row["count"] / city_total if city_total else 0
        if share < CONTRACTOR_CITY_THRESHOLD or row["count"] < CONTRACTOR_MIN_ORDERS:
            continue
        score = min(1.0, share * 5)
        anomalies.append({
            "anomaly_id": _anomaly_id(["conc_city", row["contractor"]]),
            "anomaly_type": "contractor_concentration",
            "severity": _severity(score),
            "score": round(score, 3),
            "ward_198": "",
            "ward_name": "",
            "category": "",
            "description": (
                f"{row['contractor']} holds {share:.1%} of all city orders "
                f"({row['count']}/{city_total}) totalling Rs {row['total']/1e5:,.0f}L"
            ),
            "details": {
                "contractor": row["contractor"],
                "orders": int(row["count"]),
                "city_total_orders": city_total,
                "share": round(share, 4),
                "value": float(row["total"]),
            },
        })

    logger.info(f"Contractor concentration: {len(anomalies)} flagged")
    return anomalies


# Detector 3: Duplicate Work

def detect_duplicate_work(df):
    anomalies = []
    df_valid = df.dropna(subset=["name_of_work", "ward_198"]).copy()
    df_valid = df_valid[df_valid["name_of_work"].str.strip() != ""]

    for col in ["order_date", "start_date"]:
        if col in df_valid.columns:
            df_valid[col] = pd.to_datetime(df_valid[col], errors="coerce")

    date_col = "order_date" if "order_date" in df_valid.columns else "start_date"
    seen_pairs = set()

    for ward, group in df_valid.groupby("ward_198"):
        if pd.isna(ward) or len(group) < 2:
            continue
        records = group.to_dict("records")
        tokens_cache = []
        for rec in records:
            tokens_cache.append(set(_extract_tokens(rec.get("name_of_work", ""))))

        for i in range(len(records)):
            for j in range(i + 1, min(i + 50, len(records))):
                d_i = records[i].get(date_col)
                d_j = records[j].get(date_col)
                if pd.notna(d_i) and pd.notna(d_j):
                    delta = abs((d_i - d_j).days)
                    if delta > DUPLICATE_TIME_WINDOW_DAYS:
                        continue
                text_sim = _jaccard(tokens_cache[i], tokens_cache[j])
                if text_sim < DUPLICATE_SIMILARITY_THRESHOLD:
                    continue
                g_i = records[i].get("gross", 0) or 0
                g_j = records[j].get("gross", 0) or 0
                amount_sim = 0.0
                if g_i > 0 and g_j > 0:
                    amount_sim = min(g_i, g_j) / max(g_i, g_j)
                pair_key = tuple(sorted([
                    str(records[i].get("job_number", i)),
                    str(records[j].get("job_number", j)),
                ]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                combined = 0.6 * text_sim + 0.4 * amount_sim
                score = min(1.0, combined)
                ward_name = records[i].get("ward_name", "")
                anomalies.append({
                    "anomaly_id": _anomaly_id(["dup", ward, pair_key[0], pair_key[1]]),
                    "anomaly_type": "duplicate_work",
                    "severity": _severity(score),
                    "score": round(score, 3),
                    "ward_198": str(ward),
                    "ward_name": ward_name,
                    "category": records[i].get("category", ""),
                    "description": (
                        f"Potential duplicate in {_ward_label(ward, ward_name)}: "
                        f"'{str(records[i].get('name_of_work', ''))[:60]}' vs "
                        f"'{str(records[j].get('name_of_work', ''))[:60]}' "
                        f"(text: {text_sim:.0%}, amount: Rs {g_i/1e5:,.1f}L vs Rs {g_j/1e5:,.1f}L)"
                    ),
                    "details": {
                        "text_similarity": round(text_sim, 3),
                        "amount_similarity": round(amount_sim, 3),
                        "combined_score": round(combined, 3),
                        "amount_i": float(g_i),
                        "amount_j": float(g_j),
                    },
                })

    logger.info(f"Duplicate work: {len(anomalies)} flagged")
    return anomalies


# Detector 4: Payment Speed

def detect_payment_speed(df):
    anomalies = []
    for bill_col, pay_col in [("br_date", "payment_date"), ("order_date", "start_date")]:
        if bill_col not in df.columns or pay_col not in df.columns:
            continue
        df_temp = df.copy()
        df_temp[bill_col] = pd.to_datetime(df_temp[bill_col], errors="coerce")
        df_temp[pay_col] = pd.to_datetime(df_temp[pay_col], errors="coerce")
        df_temp = df_temp.dropna(subset=[bill_col, pay_col])
        if len(df_temp) < PAYMENT_SPEED_MIN_GROUP:
            continue
        df_temp["turnaround"] = (df_temp[pay_col] - df_temp[bill_col]).dt.days
        df_temp = df_temp[df_temp["turnaround"] >= 0]
        if len(df_temp) < PAYMENT_SPEED_MIN_GROUP:
            continue
        threshold = df_temp["turnaround"].quantile(PAYMENT_SPEED_PERCENTILE / 100)
        if threshold < 0:
            continue
        fastest = df_temp[df_temp["turnaround"] <= max(threshold, 1)]
        for _, row in fastest.iterrows():
            ward = row.get("ward_198", "")
            ward_name = row.get("ward_name", "")
            days = int(row["turnaround"])
            median_days = df_temp["turnaround"].median()
            score = max(0.3, min(1.0, 1 - days / max(median_days, 1)))
            anomalies.append({
                "anomaly_id": _anomaly_id(["speed", ward, bill_col, row.get("job_number", "")]),
                "anomaly_type": "payment_speed",
                "severity": _severity(score),
                "score": round(score, 3),
                "ward_198": str(ward),
                "ward_name": ward_name,
                "category": row.get("category", ""),
                "description": (
                    f"Payment in {days} day(s) in {_ward_label(ward, ward_name)} "
                    f"(median is {median_days:.0f} days, bottom {PAYMENT_SPEED_PERCENTILE}% threshold)"
                ),
                "details": {
                    "turnaround_days": days,
                    "median_days": round(median_days, 0),
                    "threshold_days": round(threshold, 0),
                    "amount": float(row.get("gross", 0) or 0),
                },
            })
        break
    logger.info(f"Payment speed: {len(anomalies)} flagged")
    return anomalies


# Detector 5: Deduction Ratio

def detect_deduction_ratio(df):
    anomalies = []
    if "deduction" not in df.columns:
        return anomalies
    df_valid = df.dropna(subset=["gross", "deduction"]).copy()
    df_valid = df_valid[(df_valid["gross"] > 0) & (df_valid["deduction"] >= 0)]
    df_valid["ded_ratio"] = df_valid["deduction"] / df_valid["gross"]

    for ward, group in df_valid.groupby("ward_198"):
        if pd.isna(ward) or len(group) < DEDUCTION_MIN_GROUP:
            continue
        q1 = group["ded_ratio"].quantile(0.25)
        q3 = group["ded_ratio"].quantile(0.75)
        iqr = q3 - q1
        if iqr < 0.001:
            continue
        upper = q3 + DEDUCTION_IQR_FACTOR * iqr
        lower = q1 - DEDUCTION_IQR_FACTOR * iqr
        outliers = group[(group["ded_ratio"] > upper) | (group["ded_ratio"] < max(lower, 0))]
        for _, row in outliers.iterrows():
            ratio = row["ded_ratio"]
            ward_name = row.get("ward_name", "")
            deviation = abs(ratio - group["ded_ratio"].median()) / (iqr or 1)
            score = min(1.0, 0.3 + 0.15 * deviation)
            anomalies.append({
                "anomaly_id": _anomaly_id(["ded", ward, row.get("job_number", ""), ratio]),
                "anomaly_type": "deduction_ratio",
                "severity": _severity(score),
                "score": round(score, 3),
                "ward_198": str(ward),
                "ward_name": ward_name,
                "category": row.get("category", ""),
                "description": (
                    f"Deduction ratio {ratio:.1%} on Rs {row['gross']/1e5:,.1f}L order "
                    f"in {_ward_label(ward, ward_name)} "
                    f"(ward median: {group['ded_ratio'].median():.1%})"
                ),
                "details": {
                    "deduction_ratio": round(ratio, 4),
                    "ward_median_ratio": round(group["ded_ratio"].median(), 4),
                    "amount": float(row["gross"]),
                    "deduction": float(row["deduction"]),
                },
            })
    logger.info(f"Deduction ratio: {len(anomalies)} flagged")
    return anomalies


# Detector 6: Benford's Law

def detect_benford_violations(df):
    anomalies = []
    benford_expected = {d: np.log10(1 + 1 / d) for d in range(1, 10)}
    df_valid = df.dropna(subset=["gross"]).copy()
    df_valid = df_valid[df_valid["gross"] >= 1000]

    for ward, group in df_valid.groupby("ward_198"):
        if pd.isna(ward) or len(group) < BENFORD_MIN_SAMPLE:
            continue
        digits = group["gross"].apply(lambda x: int(str(int(abs(x)))[0]))
        observed = digits.value_counts().reindex(range(1, 10), fill_value=0)
        total = observed.sum()
        if total < BENFORD_MIN_SAMPLE:
            continue
        chi2 = 0
        for d in range(1, 10):
            expected_count = benford_expected[d] * total
            obs_count = observed.get(d, 0)
            chi2 += (obs_count - expected_count) ** 2 / max(expected_count, 1)
        if chi2 <= BENFORD_CHI_SQUARED_THRESHOLD:
            continue
        names = group["ward_name"].dropna()
        ward_name = names.iloc[0] if len(names) > 0 else ""
        score = min(1.0, 0.3 + (chi2 - BENFORD_CHI_SQUARED_THRESHOLD) / 50)
        max_dev_digit = 1
        max_dev = 0
        for d in range(1, 10):
            exp_pct = benford_expected[d]
            obs_pct = observed.get(d, 0) / total
            dev = abs(obs_pct - exp_pct)
            if dev > max_dev:
                max_dev = dev
                max_dev_digit = d
        anomalies.append({
            "anomaly_id": _anomaly_id(["benford", ward, chi2]),
            "anomaly_type": "benford_violation",
            "severity": _severity(score),
            "score": round(score, 3),
            "ward_198": str(ward),
            "ward_name": ward_name,
            "category": "",
            "description": (
                f"Benford's law violation in {_ward_label(ward, ward_name)} "
                f"(chi2={chi2:.1f}, threshold={BENFORD_CHI_SQUARED_THRESHOLD}). "
                f"Digit {max_dev_digit} deviates most ({observed.get(max_dev_digit,0)/total:.0%} "
                f"vs expected {benford_expected[max_dev_digit]:.0%})"
            ),
            "details": {
                "chi_squared": round(chi2, 2),
                "threshold": BENFORD_CHI_SQUARED_THRESHOLD,
                "sample_size": int(total),
                "most_deviant_digit": max_dev_digit,
            },
        })
    logger.info(f"Benford violations: {len(anomalies)} flagged")
    return anomalies


# Detector 7: Split Orders

def detect_split_orders(df):
    anomalies = []
    df_valid = df.dropna(subset=["gross", "ward_198", "contractor"]).copy()

    for (ward, contractor), group in df_valid.groupby(["ward_198", "contractor"]):
        if pd.isna(ward) or len(group) < 3:
            continue
        amounts = group["gross"].values
        for threshold in SPLIT_ORDER_THRESHOLDS:
            lower_bound = threshold * (1 - SPLIT_BAND_PCT)
            in_band = [a for a in amounts if lower_bound <= a < threshold]
            if len(in_band) < 3:
                continue
            total_in_band = sum(in_band)
            names = group["ward_name"].dropna()
            ward_name = names.iloc[0] if len(names) > 0 else ""
            score = min(1.0, 0.4 + len(in_band) * 0.1)
            anomalies.append({
                "anomaly_id": _anomaly_id(["split", ward, contractor, threshold]),
                "anomaly_type": "split_order",
                "severity": _severity(score),
                "score": round(score, 3),
                "ward_198": str(ward),
                "ward_name": ward_name,
                "category": "",
                "description": (
                    f"{len(in_band)} orders by {contractor} in {_ward_label(ward, ward_name)} "
                    f"cluster just below Rs {threshold/1e5:.0f}L threshold "
                    f"(Rs {total_in_band/1e5:,.1f}L total)"
                ),
                "details": {
                    "threshold": threshold,
                    "orders_in_band": len(in_band),
                    "total_in_band": round(total_in_band, 0),
                    "contractor": contractor,
                },
            })
    logger.info(f"Split orders: {len(anomalies)} flagged")
    return anomalies


# Detector 8: Repeat Contractor

def detect_repeat_contractor(df):
    anomalies = []
    df_valid = df.dropna(subset=["contractor", "ward_198", "category"]).copy()
    df_valid = df_valid[df_valid["contractor"].str.strip() != ""]

    group_counts = df_valid.groupby(["ward_198", "category"]).size()
    agg = (
        df_valid.groupby(["ward_198", "category", "contractor"])
        .agg(count=("gross", "size"), total=("gross", "sum"))
        .reset_index()
    )

    for _, row in agg.iterrows():
        ward = row["ward_198"]
        cat = row["category"]
        total_in_group = group_counts.get((ward, cat), 0)
        if total_in_group < 5 or row["count"] < 3:
            continue
        share = row["count"] / total_in_group
        if share < 0.30:
            continue
        names = df_valid[df_valid["ward_198"] == ward]["ward_name"].dropna()
        ward_name = names.iloc[0] if len(names) > 0 else ""
        score = min(1.0, share * 1.2)
        anomalies.append({
            "anomaly_id": _anomaly_id(["repeat", ward, cat, row["contractor"]]),
            "anomaly_type": "repeat_contractor",
            "severity": _severity(score),
            "score": round(score, 3),
            "ward_198": str(ward),
            "ward_name": ward_name,
            "category": cat,
            "description": (
                f"{row['contractor']} dominates {cat} in {_ward_label(ward, ward_name)}: "
                f"{share:.0%} of orders ({row['count']}/{total_in_group}), "
                f"Rs {row['total']/1e5:,.0f}L"
            ),
            "details": {
                "contractor": row["contractor"],
                "category": cat,
                "orders": int(row["count"]),
                "group_total_orders": int(total_in_group),
                "share": round(share, 3),
                "value": float(row["total"]),
            },
        })
    logger.info(f"Repeat contractor: {len(anomalies)} flagged")
    return anomalies


# Detector 9: Repeat Work (same location gets budget year after year)

def detect_repeat_work(df):
    """Flag locations that receive repeated budget allocations across fiscal years."""
    anomalies = []
    if "fiscal_year" not in df.columns or "name_of_work" not in df.columns:
        logger.warning("Repeat work: missing fiscal_year or name_of_work columns")
        return anomalies

    df_valid = df.dropna(subset=["ward_198", "name_of_work", "fiscal_year"]).copy()
    df_valid = df_valid[df_valid["gross"] >= REPEAT_WORK_MIN_AMOUNT]
    df_valid = df_valid[df_valid["fiscal_year"].str.strip() != ""]

    for (ward, cat), group in df_valid.groupby(["ward_198", "category"]):
        if pd.isna(ward) or len(group) < REPEAT_WORK_MIN_OCCURRENCES:
            continue

        # Build token sets and cluster similar works
        records = group.to_dict("records")
        tokens = [set(_extract_tokens(r.get("name_of_work", ""))) for r in records]
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
                sim = _jaccard(tokens[i], tokens[j])
                if sim >= REPEAT_WORK_SIMILARITY:
                    cluster.append(j)
                    used.add(j)
            clusters.append(cluster)

        # Check each cluster for occurrences across fiscal years
        for cluster_indices in clusters:
            if len(cluster_indices) < REPEAT_WORK_MIN_OCCURRENCES:
                continue
            cluster_records = [records[i] for i in cluster_indices]
            fiscal_years = sorted(set(
                r.get("fiscal_year", "") for r in cluster_records
                if r.get("fiscal_year", "").strip()
            ))
            if len(fiscal_years) < REPEAT_WORK_MIN_OCCURRENCES:
                continue

            total_spend = sum(r.get("gross", 0) or 0 for r in cluster_records)
            avg_spend = total_spend / len(cluster_records) if cluster_records else 0
            sample_desc = str(cluster_records[0].get("name_of_work", ""))[:80]
            ward_name = cluster_records[0].get("ward_name", "")

            # Severity: 3yr=medium, 4yr=high, 5+=critical
            n_years = len(fiscal_years)
            if n_years >= 5:
                score = min(1.0, 0.75 + (n_years - 5) * 0.05)
            elif n_years >= 4:
                score = 0.55
            else:
                score = 0.35

            anomalies.append({
                "anomaly_id": _anomaly_id(["repeat_work", ward, cat, sample_desc[:40]]),
                "anomaly_type": "repeat_work",
                "severity": _severity(score),
                "score": round(score, 3),
                "ward_198": str(ward),
                "ward_name": ward_name,
                "category": cat,
                "description": (
                    f"Repeated {cat} work in {_ward_label(ward, ward_name)} across "
                    f"{n_years} fiscal years ({', '.join(fiscal_years[:5])}{'...' if n_years > 5 else ''}): "
                    f"'{sample_desc}' — {len(cluster_records)} orders, "
                    f"Rs {total_spend/1e5:,.1f}L total"
                ),
                "details": {
                    "fiscal_years": fiscal_years,
                    "num_years": n_years,
                    "order_count": len(cluster_records),
                    "total_spend": round(total_spend, 0),
                    "avg_spend": round(avg_spend, 0),
                    "sample_description": sample_desc,
                },
            })

    logger.info(f"Repeat work: {len(anomalies)} flagged")
    return anomalies


# Detector 10: Bid/Benchmark Anomaly

def _load_sor_benchmarks():
    """Load Karnataka SoR benchmark rates."""
    sor_path = os.path.join(PROJECT_ROOT, "benchmarks", "karnataka_sor_2024.json")
    if not os.path.exists(sor_path):
        logger.warning(f"SoR benchmark file not found: {sor_path}")
        return {}
    with open(sor_path) as f:
        data = json.load(f)
    return data.get("rates", {})


def detect_bid_anomaly(df):
    """Flag work orders significantly above benchmark rates and ward medians."""
    anomalies = []
    sor = _load_sor_benchmarks()
    if not sor:
        logger.warning("Bid anomaly: no SoR benchmarks loaded")
        return anomalies

    # Build per-category average SoR rate (simple average of all items in category)
    category_sor_avg = {}
    for cat, items in sor.items():
        rates = [v["rate_inr"] for v in items.values() if "rate_inr" in v]
        if rates:
            category_sor_avg[cat] = sum(rates) / len(rates)

    df_valid = df.dropna(subset=["ward_198", "gross", "category"]).copy()
    df_valid = df_valid[df_valid["gross"] >= BID_MIN_AMOUNT]
    df_valid = df_valid[df_valid["category"].isin(category_sor_avg.keys())]

    for (ward, cat), group in df_valid.groupby(["ward_198", "category"]):
        if pd.isna(ward) or len(group) < BID_MIN_GROUP_SIZE:
            continue

        median_cost = group["gross"].median()
        threshold = median_cost * BID_BENCHMARK_FACTOR

        outliers = group[group["gross"] > threshold]
        for _, row in outliers.iterrows():
            ratio = row["gross"] / median_cost if median_cost > 0 else 1
            ward_name = row.get("ward_name", "")
            contractor = row.get("contractor", "")

            score = min(1.0, 0.35 + 0.15 * (ratio - BID_BENCHMARK_FACTOR))

            anomalies.append({
                "anomaly_id": _anomaly_id(["bid", ward, cat, row["gross"], contractor[:20]]),
                "anomaly_type": "bid_anomaly",
                "severity": _severity(score),
                "score": round(score, 3),
                "ward_198": str(ward),
                "ward_name": ward_name,
                "category": cat,
                "description": (
                    f"Rs {row['gross']/1e5:,.1f}L {cat} order in {_ward_label(ward, ward_name)} "
                    f"is {ratio:.1f}× the ward median of Rs {median_cost/1e5:,.1f}L"
                    f"{' by ' + contractor if contractor else ''}"
                ),
                "details": {
                    "amount": float(row["gross"]),
                    "ward_median": round(median_cost, 0),
                    "ratio_to_median": round(ratio, 2),
                    "sor_avg_rate": category_sor_avg.get(cat, 0),
                    "contractor": contractor,
                    "group_size": len(group),
                },
            })

    logger.info(f"Bid anomaly: {len(anomalies)} flagged")
    return anomalies


# Main

def run_all_detectors(df):
    all_anomalies = []
    detectors = [
        detect_cost_outliers,
        detect_contractor_concentration,
        detect_duplicate_work,
        detect_payment_speed,
        detect_deduction_ratio,
        detect_benford_violations,
        detect_split_orders,
        detect_repeat_contractor,
        detect_repeat_work,
        detect_bid_anomaly,
    ]
    for detector in detectors:
        try:
            results = detector(df)
            all_anomalies.extend(results)
        except Exception as e:
            logger.error(f"Detector {detector.__name__} failed: {e}")
    all_anomalies.sort(key=lambda a: a.get("score", 0), reverse=True)
    logger.info(f"Total anomalies: {len(all_anomalies)}")
    return all_anomalies


def main():
    csv_path = os.path.join(PROCESSED_DIR, "all_work_orders.csv")
    if not os.path.exists(csv_path):
        logger.error(f"Processed CSV not found: {csv_path}")
        return

    logger.info(f"Loading {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    logger.info(f"Loaded {len(df)} records, columns: {list(df.columns)}")

    for col in ["gross", "deduction", "nett"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    anomalies = run_all_detectors(df)

    out_path = os.path.join(PROCESSED_DIR, "anomalies.json")
    with open(out_path, "w") as f:
        json.dump(anomalies, f, indent=2, default=str)
    logger.info(f"Saved {len(anomalies)} anomalies to {out_path}")


if __name__ == "__main__":
    main()

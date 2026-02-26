"""Process BBMP tender NIT data and cross-reference with work orders.

Reads 5 yearly CSVs from data/raw/bbmp_tenders/, normalizes them,
extracts ward numbers from tender titles, maps department-location to zones,
and cross-references with work orders to produce estimated-vs-actual cost
gap analysis.

Output: data/site/tenders.json
"""

import csv
import glob
import json
import logging
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PROJECT_ROOT, PROCESSED_DIR, SITE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TENDER_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "bbmp_tenders")
WARD_MAPPING_PATH = os.path.join(PROJECT_ROOT, "benchmarks", "ward_mapping.json")

# ── Department-Location → Zone mapping ─────────────────────────────────────
# Derived from the 82 unique dept-location values in the tender CSVs.
# These map BBMP engineering divisions to the 8 BBMP zones.
DEPT_TO_ZONE = {
    "BBMP-EE-MAHADEVAPURA": "Mahadevapura",
    "BBMP-EE-BTMLAYOUT": "Bommanahalli",
    "BBMP-EE-Chamarajpeth": "West",
    "BBMP-EE-BNG SOUTH": "South",
    "BBMP-EE-BOMMANAHALLI": "Bommanahalli",
    "BBMP-EE-MR-SPL": "West",      # Malleswaram Special Division
    "BBMP-EE-SARVAGNANAGAR": "East",
    "BBMP-EE-YELAHANKA": "Yelahanka",
    "BBMP-EE-BYATRAYANAPURA": "Yelahanka",
    "BBMP-EE-CVRAMANNAGAR": "East",
    "BBMP-EE-RRNAGAR": "RR Nagar",
    "BBMP-EE-DASARAHALLI": "Dasarahalli",
    "BBMP-EE-PULIKESHINAGAR": "East",
    "BBMP-EE-PDMBNGR": "Bommanahalli",
    "BBMP-EE-KRPURAM": "Mahadevapura",
    "BBMP-Corporation-Off": "West",  # Central office
    "BBMP-EE-SHIVAJINAGAR": "East",
    "BBMP-EE-Chandra-Layout-South": "RR Nagar",
    "EE-BASAVANAGUDI1": "South",
    "BBMP-EE-HEBBALA-EAST-ZN": "Yelahanka",
    "BBMP-EE-GANDHINAGAR": "East",
    "BBMP-EE-MALLESHWARAM": "West",
    "BBMP-EE-GOVINDRAJNAGAR": "West",
    "BBMP-EE-BNG EAST": "East",
    "BBMP-EE-KENGERI": "RR Nagar",
    "BBMP-EE-JAYANAGAR": "South",
    "BBMP-EE-CHICKPETE": "West",
    "BBMP-EE-RAJAJINAGAR": "West",
    "BBMP-EE-HEBBAL": "Yelahanka",
    "BBMP-EE-VIJAYNAGAR": "West",
    "BBMP-EE-YESHWANTHPURA": "Dasarahalli",
    "BBMP-SE-MAHADEVAPURA": "Mahadevapura",
    "BBMP-SE-BOMMANAHALLI": "Bommanahalli",
    "BBMP-SE-SOUTH": "South",
    "BBMP-SE-EAST": "East",
    "BBMP-SE-WEST": "West",
    "BBMP-SE-YELAHANKA": "Yelahanka",
    "BBMP-SE-RRNAGAR": "RR Nagar",
    "BBMP-SE-DASARAHALLI": "Dasarahalli",
    "BBMP-HEALTH": "West",
    "BBMP-SWM": "West",
    "BBMP-EE-SWD": "West",         # Storm Water Drain division
    "BBMP-EE-LAKES": "West",
    "BBMP-MAJOR-ROADS": "West",
    "BBMP-EE-KORAMANGALA": "South",
    "BBMP-EE-WHITEFIELD": "Mahadevapura",
}


def _normalize_fy(fy_str):
    """Convert '2013-2014' → '2013-14' to match work order format."""
    m = re.match(r"(\d{4})-(\d{4})", fy_str)
    if m:
        return f"{m.group(1)}-{m.group(2)[2:]}"
    return fy_str


def _extract_ward(title):
    """Extract ward number from tender title text.

    Common patterns:
    - 'ward no 45', 'ward no. 45', 'ward-45', 'Ward No:45'
    - 'Ward 45', 'wardno45', 'Ward No-45'
    """
    if not title:
        return None
    m = re.search(r"ward\s*(?:no\.?\s*[-:]?\s*)?(\d{1,3})", title, re.I)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 198:
            return num
    return None


def _parse_value(val_str):
    """Parse tender value string to float. Returns None for unparseable values."""
    if not val_str:
        return None
    val_str = val_str.replace(",", "").strip()
    if val_str.lower() in ("not available", "na", "n/a", "-", ""):
        return None
    try:
        v = float(val_str)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _map_tender_category(category, sub_category):
    """Map tender Category/Sub-Category to work order categories."""
    sub = (sub_category or "").lower()
    if "road" in sub:
        return "roads"
    if "drain" in sub or "sewage" in sub or "swd" in sub or "storm" in sub:
        return "drainage"
    if "building" in sub:
        return "buildings"
    if "electri" in sub or "light" in sub:
        return "lighting"
    if "water" in sub and "storm" not in sub:
        return "water"
    if "bridge" in sub or "culvert" in sub:
        return "roads"
    if "tank" in sub or "lake" in sub:
        return "water"
    cat = (category or "").lower()
    if cat == "services":
        return "other"
    if cat == "goods":
        return "other"
    return "other"


def _guess_zone(dept_loc):
    """Map department-location to zone using the lookup table."""
    if not dept_loc:
        return None
    # Try exact match
    if dept_loc in DEPT_TO_ZONE:
        return DEPT_TO_ZONE[dept_loc]
    # Try partial match
    dl_upper = dept_loc.upper()
    for key, zone in DEPT_TO_ZONE.items():
        if key.upper() in dl_upper or dl_upper in key.upper():
            return zone
    return None


def load_tenders():
    """Load and normalize all tender CSVs."""
    pattern = os.path.join(TENDER_DIR, "*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        logger.error(f"No tender CSVs found in {TENDER_DIR}")
        sys.exit(1)

    all_tenders = []
    for fpath in files:
        fy_match = re.search(r"(\d{4}-\d{4})", os.path.basename(fpath))
        fy_raw = fy_match.group(1) if fy_match else "unknown"
        fy = _normalize_fy(fy_raw)

        with open(fpath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = row.get("Tender Title", "")
                value = _parse_value(row.get("Tender Value in Rs", ""))
                ward = _extract_ward(title)
                category = _map_tender_category(
                    row.get("Category", ""),
                    row.get("Sub-Category", ""),
                )
                dept_loc = row.get("Department-Location", "")
                zone = _guess_zone(dept_loc)
                tender_type = row.get("Tender Type", "OPEN")

                all_tenders.append({
                    "title": title.strip(),
                    "value": value,
                    "ward": ward,
                    "zone": zone,
                    "category": category,
                    "fy": fy,
                    "dept_location": dept_loc,
                    "published_date": row.get("Published Date", ""),
                    "tender_number": row.get("Tender Number", ""),
                    "tender_type": tender_type,
                    "sub_category": row.get("Sub-Category", ""),
                })

    logger.info(f"Loaded {len(all_tenders)} tenders from {len(files)} files")
    return all_tenders


def load_work_orders():
    """Load processed work orders for cross-referencing."""
    csv_path = os.path.join(PROCESSED_DIR, "all_work_orders.csv")
    if not os.path.exists(csv_path):
        logger.warning(f"Work orders not found: {csv_path}")
        return []

    orders = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gross = 0
            try:
                gross = float(row.get("gross", 0) or 0)
            except (ValueError, TypeError):
                pass
            ward = None
            try:
                ward = int(float(row.get("ward_198", 0) or 0))
                if ward < 1 or ward > 198:
                    ward = None
            except (ValueError, TypeError):
                ward = None

            orders.append({
                "ward": ward,
                "category": row.get("category", "other"),
                "fy": row.get("fiscal_year", ""),
                "gross": gross,
                "name_of_work": row.get("name_of_work", ""),
                "contractor": row.get("contractor", ""),
            })

    logger.info(f"Loaded {len(orders)} work orders")
    return orders


def load_ward_mapping():
    """Load ward name and zone mapping."""
    if not os.path.exists(WARD_MAPPING_PATH):
        return {}, {}
    with open(WARD_MAPPING_PATH) as f:
        data = json.load(f)
    return data.get("ward_198_to_name", {}), data.get("ward_198_to_zone", {})


def build_gap_analysis(tenders, orders, ward_names, ward_zones):
    """Cross-reference tender estimated values with actual work order spending.

    Groups by ward + FY and compares total estimated tender value with
    total actual work order gross amount.
    """
    # Overlap fiscal years (tenders only cover 2013-14 through 2017-18)
    tender_fys = {"2013-14", "2014-15", "2015-16", "2016-17", "2017-18"}

    # Build ward+FY→tender aggregate
    tender_agg = defaultdict(lambda: {"count": 0, "total_value": 0})
    for t in tenders:
        if t["ward"] and t["value"] and t["fy"] in tender_fys:
            key = (t["ward"], t["fy"])
            tender_agg[key]["count"] += 1
            tender_agg[key]["total_value"] += t["value"]

    # Build ward+FY→work order aggregate
    wo_agg = defaultdict(lambda: {"count": 0, "total_gross": 0})
    for o in orders:
        if o["ward"] and o["fy"] in tender_fys:
            key = (o["ward"], o["fy"])
            wo_agg[key]["count"] += 1
            wo_agg[key]["total_gross"] += o["gross"]

    # Compare: find wards where actual spend significantly exceeds tender estimates
    gap_records = []
    for (ward, fy), t_data in tender_agg.items():
        wo_data = wo_agg.get((ward, fy))
        if not wo_data or wo_data["total_gross"] == 0:
            continue
        estimated = t_data["total_value"]
        actual = wo_data["total_gross"]
        if estimated == 0:
            continue

        gap_pct = ((actual - estimated) / estimated) * 100
        gap_records.append({
            "ward": ward,
            "ward_name": ward_names.get(str(ward), f"Ward {ward}"),
            "zone": ward_zones.get(str(ward), ""),
            "fy": fy,
            "tender_count": t_data["count"],
            "tender_total_lakhs": round(estimated / 1e5, 1),
            "wo_count": wo_data["count"],
            "actual_total_lakhs": round(actual / 1e5, 1),
            "gap_pct": round(gap_pct, 1),
            "gap_lakhs": round((actual - estimated) / 1e5, 1),
        })

    gap_records.sort(key=lambda x: x["gap_pct"], reverse=True)
    logger.info(f"Gap analysis: {len(gap_records)} ward-FY comparisons")
    return gap_records


def build_zone_analysis(tenders, orders):
    """Aggregate tender data by zone and compare with work order spending."""
    tender_fys = {"2013-14", "2014-15", "2015-16", "2016-17", "2017-18"}

    zone_tenders = defaultdict(lambda: {"count": 0, "total_value": 0})
    for t in tenders:
        if t["zone"] and t["value"] and t["fy"] in tender_fys:
            zone_tenders[t["zone"]]["count"] += 1
            zone_tenders[t["zone"]]["total_value"] += t["value"]

    zone_wo = defaultdict(lambda: {"count": 0, "total_gross": 0})
    # Need to map work order wards to zones
    ward_names, ward_zones = load_ward_mapping()
    for o in orders:
        if o["ward"] and o["fy"] in tender_fys:
            zone = ward_zones.get(str(o["ward"]), "")
            if zone:
                zone_wo[zone]["count"] += 1
                zone_wo[zone]["total_gross"] += o["gross"]

    zones = {}
    all_zones = set(zone_tenders.keys()) | set(zone_wo.keys())
    for z in sorted(all_zones):
        t = zone_tenders.get(z, {"count": 0, "total_value": 0})
        w = zone_wo.get(z, {"count": 0, "total_gross": 0})
        estimated = t["total_value"]
        actual = w["total_gross"]
        gap_pct = ((actual - estimated) / estimated * 100) if estimated > 0 else None
        zones[z] = {
            "tender_count": t["count"],
            "tender_value_lakhs": round(estimated / 1e5, 1),
            "wo_count": w["count"],
            "actual_spend_lakhs": round(actual / 1e5, 1),
            "gap_pct": round(gap_pct, 1) if gap_pct is not None else None,
        }

    return zones


def build_summary(tenders):
    """Build high-level summary statistics."""
    total = len(tenders)
    with_value = sum(1 for t in tenders if t["value"])
    total_value = sum(t["value"] for t in tenders if t["value"])
    with_ward = sum(1 for t in tenders if t["ward"])

    by_fy = defaultdict(lambda: {"count": 0, "value": 0})
    for t in tenders:
        by_fy[t["fy"]]["count"] += 1
        if t["value"]:
            by_fy[t["fy"]]["value"] += t["value"]

    by_category = defaultdict(lambda: {"count": 0, "value": 0})
    for t in tenders:
        by_category[t["category"]]["count"] += 1
        if t["value"]:
            by_category[t["category"]]["value"] += t["value"]

    return {
        "total_tenders": total,
        "with_value": with_value,
        "total_value_lakhs": round(total_value / 1e5, 1),
        "with_ward": with_ward,
        "by_fy": {
            fy: {"count": d["count"], "value_lakhs": round(d["value"] / 1e5, 1)}
            for fy, d in sorted(by_fy.items())
        },
        "by_category": {
            cat: {"count": d["count"], "value_lakhs": round(d["value"] / 1e5, 1)}
            for cat, d in sorted(by_category.items(), key=lambda x: -x[1]["value"])
        },
    }


def build_records_sample(tenders, limit=5000):
    """Build a sample of tender records for the data table.

    Prioritizes tenders with both ward number and value available.
    """
    # Sort: tenders with ward+value first, then by value descending
    scored = []
    for t in tenders:
        score = (2 if t["ward"] and t["value"] else
                 1 if t["ward"] or t["value"] else 0)
        scored.append((score, t["value"] or 0, t))
    scored.sort(key=lambda x: (-x[0], -x[1]))

    records = []
    for _, _, t in scored[:limit]:
        records.append({
            "title": t["title"][:120],  # Truncate for JSON size
            "value_lakhs": round(t["value"] / 1e5, 1) if t["value"] else None,
            "ward": t["ward"],
            "zone": t["zone"],
            "category": t["category"],
            "fy": t["fy"],
            "published_date": t["published_date"],
            "tender_type": t["tender_type"],
            "sub_category": t["sub_category"],
        })
    return records


def main():
    tenders = load_tenders()
    orders = load_work_orders()
    ward_names, ward_zones = load_ward_mapping()

    summary = build_summary(tenders)
    gap_analysis = build_gap_analysis(tenders, orders, ward_names, ward_zones)
    zone_analysis = build_zone_analysis(tenders, orders)
    records = build_records_sample(tenders)

    # Top cost overruns (actual >> estimated) — corruption red flags
    top_overruns = [g for g in gap_analysis if g["gap_pct"] > 50][:50]

    # Top under-spending (estimated >> actual) — possible fund diversion
    top_underspend = sorted(
        [g for g in gap_analysis if g["gap_pct"] < -30],
        key=lambda x: x["gap_pct"]
    )[:50]

    output = {
        "summary": summary,
        "gap_analysis": gap_analysis,
        "zone_analysis": zone_analysis,
        "top_overruns": top_overruns,
        "top_underspend": top_underspend,
        "records": records,
    }

    os.makedirs(SITE_DIR, exist_ok=True)
    out_path = os.path.join(SITE_DIR, "tenders.json")
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    # Also copy to docs/data/ for GitHub Pages static site
    docs_data_dir = os.path.join(PROJECT_ROOT, "docs", "data")
    if os.path.isdir(docs_data_dir):
        import shutil
        shutil.copy2(out_path, os.path.join(docs_data_dir, "tenders.json"))
        logger.info(f"Copied to {docs_data_dir}/tenders.json")

    logger.info(f"Wrote {out_path} ({os.path.getsize(out_path) / 1024:.0f} KB)")
    logger.info(f"  Summary: {summary['total_tenders']} tenders, "
                f"₹{summary['total_value_lakhs']:.0f}L total value")
    logger.info(f"  Gap analysis: {len(gap_analysis)} ward-FY comparisons")
    logger.info(f"  Overruns (>50%): {len(top_overruns)}, Underspend (<-30%): {len(top_underspend)}")
    logger.info(f"  Records sample: {len(records)}")


if __name__ == "__main__":
    main()

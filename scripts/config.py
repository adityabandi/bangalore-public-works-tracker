"""Central configuration for the BBMP Public Works Tracker."""

import os

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
SITE_DIR = os.path.join(DATA_DIR, "site")
BENCHMARKS_DIR = os.path.join(PROJECT_ROOT, "benchmarks")
HASHES_FILE = os.path.join(DATA_DIR, "hashes.json")
FETCH_STATUS_FILE = os.path.join(DATA_DIR, "fetch_status.json")

# CKAN dataset package IDs on data.opencity.in
DATASETS = {
    "ward_2013_2022": {
        "package_id": "bbmp-work-orders-by-ward-2013-2022",
        "ward_regime": 198,
        "priority": 1,
        "description": "Work orders by ward, 2013-2022 (198 CSVs)",
    },
    "2023_24": {
        "package_id": "bbmp-work-orders-2023-24",
        "ward_regime": 198,
        "priority": 2,
        "description": "Work orders 2023-24",
    },
    "2024_25": {
        "package_id": "bbmp-work-orders-and-payments-2024-25",
        "ward_regime": None,  # Mixed: files for 198, 225, and 243 regimes
        "priority": 3,
        "description": "Work orders 2024-25 (multi-regime)",
    },
}

# Column name normalization map: variations -> canonical name
COLUMN_MAP = {
    # ID fields
    "_id": "_id",
    "id": "_id",
    "sl no": "sl_no",
    "sl. no": "sl_no",
    "sl.no": "sl_no",
    "sl no.": "sl_no",
    "slno": "sl_no",
    "serial no": "sl_no",
    "job number": "job_number",
    "job no": "job_number",
    "job_number": "job_number",

    # Work details
    "name of work": "name_of_work",
    "name of the work": "name_of_work",
    "work name": "name_of_work",
    "work description": "name_of_work",
    "wodetails": "name_of_work",

    # Location
    "ward": "ward",
    "ward no": "ward",
    "ward number": "ward",
    "ward name": "ward",
    "office": "office",
    "budget head": "budget_head",

    # Contractor
    "contractor": "contractor",
    "contractor name": "contractor",
    "name of contractor": "contractor",
    "mobile": "mobile",
    "mobile no": "mobile",
    "email": "email",
    "email id": "email",

    # Bill info
    "bill type": "bill_type",
    "type of bill": "bill_type",
    "order number": "order_number",
    "order no": "order_number",
    "order date": "order_date",

    # Dates
    "start date": "start_date",
    "end date": "end_date",
    "sbr number": "sbr_number",
    "sbr no": "sbr_number",
    "sbr date": "sbr_date",
    "br number": "br_number",
    "br no": "br_number",
    "brnumber": "br_number",
    "br date": "br_date",
    "cbr number": "cbr_number",
    "cbr no": "cbr_number",
    "cbr date": "cbr_date",
    "payment": "payment_date",
    "payment date": "payment_date",

    # Amounts
    "gross": "gross",
    "gross amount": "gross",
    "amount": "gross",
    "gross in words": "gross_words",
    "deduction": "deduction",
    "deduction amount": "deduction",
    "deduction in words": "deduction_words",
    "nett": "nett",
    "net": "nett",
    "net amount": "nett",
    "nett in words": "nett_words",
    "net in words": "nett_words",
}

# Anomaly detection thresholds
COST_OUTLIER_IQR_FACTOR = 3.0       # Flag if amount > Q3 + factor * IQR
COST_OUTLIER_MIN_AMOUNT = 500000    # Ignore amounts < 5 lakh INR
COST_OUTLIER_MIN_GROUP_SIZE = 10    # Need >= N records in group for analysis

CONTRACTOR_WARD_THRESHOLD = 0.15    # Flag if >15% of ward orders
CONTRACTOR_CITY_THRESHOLD = 0.05    # Flag if >5% of city-wide orders
CONTRACTOR_MIN_ORDERS = 5           # Only flag contractors with >= N orders

DUPLICATE_SIMILARITY_THRESHOLD = 0.85  # Jaccard similarity threshold
DUPLICATE_TIME_WINDOW_DAYS = 365       # Look within 12 months

PAYMENT_SPEED_PERCENTILE = 5        # Flag bottom 5% (suspiciously fast)
PAYMENT_SPEED_MIN_GROUP = 20        # Need >= N records for analysis

DEDUCTION_IQR_FACTOR = 2.5          # Flag unusual deduction ratios
DEDUCTION_MIN_GROUP = 20            # Need >= N records for analysis

BENFORD_CHI_SQUARED_THRESHOLD = 15.51  # 8 df, 0.05 significance
BENFORD_MIN_SAMPLE = 100              # Need >= N records per ward

# Output limits
ANOMALIES_FEED_LIMIT = 999999       # All anomalies (gzipped ~250KB — fine for static site)
CONTRACTORS_LIMIT = 999999          # All contractors (gzipped ~195KB — fine for static site)
TOP_CONTRACTORS_PER_WARD = 5        # Top N contractors per ward

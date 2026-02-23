"""Normalize and merge all BBMP work order CSVs into a canonical dataset."""

import glob
import hashlib
import json
import logging
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DATASETS, RAW_DIR, PROCESSED_DIR, COLUMN_MAP,
)
from utils.amount_parser import parse_indian_amount
from utils.text_classifier import classify_work
from utils.ward_mapper import WardMapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Known header markers for detecting the real header row in BBMP CSVs
_HEADER_MARKERS = {"sl no", "name of work", "gross", "ward", "contractor",
                   "wodetails", "amount", "slno", "brnumber"}


def normalize_column_name(col: str) -> str:
    """Map raw CSV column names to canonical names."""
    key = col.strip().lower().replace("_", " ")
    return COLUMN_MAP.get(key, key.replace(" ", "_"))


def detect_ward_regime_from_filename(filename: str) -> int | None:
    """Detect ward regime from filename for mixed-regime datasets."""
    name = filename.lower()
    if "198" in name:
        return 198
    if "225" in name:
        return 225
    if "243" in name:
        return 243
    return None


def _find_header_row(path: str, encoding: str = "utf-8") -> int:
    """Determine which logical CSV row contains the real header.

    Many ward_2013_2022 CSVs have 1-3 junk banner rows (which may
    contain quoted multiline text) before the real column headers.
    We read the first few rows with no header and check which one
    contains known column names.

    Returns the 0-based logical row index of the header.
    """
    try:
        # Read first 10 logical rows with no header
        probe = pd.read_csv(path, dtype=str, encoding=encoding,
                            header=None, nrows=10)
        for row_idx in range(min(10, len(probe))):
            cells = [str(v).strip().lower() for v in probe.iloc[row_idx].tolist()
                     if pd.notna(v)]
            matches = sum(1 for c in cells if c in _HEADER_MARKERS)
            if matches >= 2:
                return row_idx
    except Exception:
        pass
    return 0


def read_csv_safe(path: str) -> pd.DataFrame | None:
    """Read a CSV with encoding fallbacks and automatic junk-row skipping."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            header_row = _find_header_row(path, encoding)
            df = pd.read_csv(path, dtype=str, encoding=encoding,
                             header=header_row)
            if len(df) == 0:
                continue

            # Drop a leading unnamed index column (common in ward_2013_2022)
            first_col = df.columns[0]
            if first_col == "0" or first_col.startswith("Unnamed"):
                # Check if the column is just sequential row numbers
                try:
                    vals = df[first_col].dropna()
                    if len(vals) > 0 and vals.str.match(r"^\d+$").all():
                        df = df.drop(columns=[first_col])
                except Exception:
                    pass

            return df
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return None
    logger.warning(f"Could not read {path} with any encoding")
    return None


def clean_html(text: str) -> str:
    """Strip HTML tags and artifacts from text fields."""
    if not isinstance(text, str):
        return text
    return re.sub(r"<[^>]+>", "", text).strip()


def process_dataset(dataset_key: str, config: dict, ward_mapper: WardMapper) -> pd.DataFrame:
    """Load and normalize all CSVs for a single dataset."""
    raw_dir = os.path.join(RAW_DIR, dataset_key)
    if not os.path.exists(raw_dir):
        logger.warning(f"Raw directory not found: {raw_dir}")
        return pd.DataFrame()

    csv_files = glob.glob(os.path.join(raw_dir, "*.csv"))
    if not csv_files:
        logger.warning(f"No CSV files in {raw_dir}")
        return pd.DataFrame()

    frames = []
    for csv_path in csv_files:
        df = read_csv_safe(csv_path)
        if df is None or df.empty:
            continue

        # Normalize column names (maps wodetails->name_of_work, amount->gross, etc.)
        df.columns = [normalize_column_name(c) for c in df.columns]

        # Extract job number from name_of_work if embedded (2023-24/2024-25 format)
        # Format: "160-23-000005</a>Comprehensive Development of Roads..."
        if "name_of_work" in df.columns and "job_number" not in df.columns:
            job_pattern = re.compile(r'^(\d{3}-\d{2}-\d{6})</a>')
            extracted = df["name_of_work"].str.extract(job_pattern.pattern, expand=False)
            if extracted.notna().any():
                df["job_number"] = extracted
                # Remove the job number prefix and HTML tag from name_of_work
                df["name_of_work"] = df["name_of_work"].str.replace(
                    r'^\d{3}-\d{2}-\d{6}</a>', '', regex=True
                ).str.strip()

        # Strip remaining HTML artifacts from name_of_work
        if "name_of_work" in df.columns:
            df["name_of_work"] = df["name_of_work"].apply(clean_html)

        # Check for minimum required columns AFTER column mapping
        has_work = "name_of_work" in df.columns
        has_amount = "gross" in df.columns or "nett" in df.columns
        if not has_work and not has_amount:
            logger.warning(f"Skipping {csv_path}: missing name_of_work and gross/nett columns. "
                           f"Available: {list(df.columns)}")
            continue

        # Parse composite br_number field (2023-24/2024-25 format)
        # Format: "BR - 000186 / 26-Dec-2022CBR - / Rtgs - 001514 / 01-Apr-2023"
        if "br_number" in df.columns and "payment_date" not in df.columns:
            br_raw = df["br_number"].fillna("")
            # Extract BR number & date
            br_match = br_raw.str.extract(r'BR\s*-\s*(\d+)\s*/\s*(\d{2}-\w{3}-\d{4})')
            if "br_number" not in df.columns or br_match[0].notna().any():
                df["br_number"] = br_match[0]
                df["br_date"] = br_match[1]
            # Extract payment info from Rtgs
            rtgs_match = br_raw.str.extract(r'Rtgs?\s*-\s*(\d+)\s*/\s*(\d{2}-\w{3}-\d{4})')
            if rtgs_match[0].notna().any():
                df["payment_date"] = rtgs_match[1]

        # Parse amounts
        for col in ("gross", "deduction", "nett"):
            if col in df.columns:
                df[col] = df[col].apply(parse_indian_amount)
            else:
                df[col] = 0.0

        # Parse dates
        date_cols = ["start_date", "end_date", "order_date", "payment_date",
                     "sbr_date", "br_date", "cbr_date"]
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], format="mixed", dayfirst=True, errors="coerce")

        # Determine ward regime for this file
        regime = config.get("ward_regime")
        if regime is None:
            regime = detect_ward_regime_from_filename(os.path.basename(csv_path))
            if regime is None:
                regime = 198  # default

        # Normalize ward numbers
        if "ward" in df.columns:
            ward_info = df["ward"].apply(lambda w: ward_mapper.normalize_ward(w, regime))
            ward_df = pd.DataFrame(ward_info.tolist())
            for c in ward_df.columns:
                df[c] = ward_df[c]
        else:
            df["ward_198"] = None
            df["ward_name"] = None
            df["zone"] = None

        # Classify work type
        if "name_of_work" in df.columns:
            df["category"] = df["name_of_work"].apply(classify_work)
        else:
            df["category"] = "other"

        # Normalize contractor names
        if "contractor" in df.columns:
            df["contractor"] = (
                df["contractor"]
                .fillna("")
                .str.upper()
                .str.strip()
                .str.replace(r"[^\w\s]", "", regex=True)
                .str.replace(r"\s+", " ", regex=True)
            )
        else:
            df["contractor"] = ""

        # Add provenance
        df["source_dataset"] = dataset_key
        df["source_file"] = os.path.basename(csv_path)

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    logger.info(f"  {dataset_key}: {len(merged)} records from {len(frames)} files")
    return merged


def generate_id(row) -> str:
    """Generate a deterministic unique ID for a work order."""
    parts = [
        str(row.get('job_number', '') or ''),
        str(row.get('ward_198', '') or ''),
        str(row.get('name_of_work', '') or '')[:80],
        str(row.get('gross', '') or ''),
        str(row.get('contractor', '') or '')[:40],
        str(row.get('source_dataset', '') or ''),
    ]
    key = "|".join(parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate records across datasets.

    Uses a composite key that works across all CSV formats.
    Records with job_number use that + ward + order_date.
    Records without job_number use name_of_work + ward + gross + contractor.
    """
    before = len(df)

    def _make_key(r):
        jn = str(r.get('job_number', '') or '').strip()
        ward = str(r.get('ward_198', '') or '').strip()
        if jn:
            # ward_2013_2022 records — keyed by job number
            return f"JN|{jn}|{ward}|{str(r.get('order_date', ''))}"
        else:
            # 2023-24/2024-25 records — keyed by work description + amount
            work = str(r.get('name_of_work', '') or '')[:80].strip()
            gross = str(r.get('gross', '') or '').strip()
            contractor = str(r.get('contractor', '') or '')[:40].strip()
            br = str(r.get('br_number', '') or '').strip()
            return f"WO|{ward}|{work}|{gross}|{contractor}|{br}"

    df["_dedup_key"] = df.apply(_make_key, axis=1)

    # Prefer records from more recent datasets (higher priority)
    priority_map = {k: v["priority"] for k, v in DATASETS.items()}
    df["_priority"] = df["source_dataset"].map(priority_map).fillna(0)

    df = df.sort_values("_priority", ascending=False).drop_duplicates("_dedup_key", keep="first")
    df = df.drop(columns=["_dedup_key", "_priority"])

    after = len(df)
    if before != after:
        logger.info(f"Deduplication: {before} -> {after} records ({before - after} removed)")

    return df


def derive_fiscal_year(date_val) -> str:
    """Derive fiscal year string from a date. E.g., 2023-07-15 -> '2023-24'."""
    if pd.isna(date_val):
        return ""
    if date_val.month >= 4:
        return f"{date_val.year}-{str(date_val.year + 1)[-2:]}"
    return f"{date_val.year - 1}-{str(date_val.year)[-2:]}"


def normalize_all():
    """Run the full normalization pipeline."""
    ward_mapper = WardMapper()
    all_frames = []

    for dataset_key, config in sorted(DATASETS.items(), key=lambda x: x[1]["priority"]):
        logger.info(f"Processing: {dataset_key}")
        df = process_dataset(dataset_key, config, ward_mapper)
        if not df.empty:
            all_frames.append(df)

    if not all_frames:
        logger.error("No data loaded from any dataset")
        return

    merged = pd.concat(all_frames, ignore_index=True)
    logger.info(f"Total records before dedup: {len(merged)}")

    merged = deduplicate(merged)

    # Generate IDs
    merged["id"] = merged.apply(generate_id, axis=1)

    # Derive fiscal year — try order_date first, fallback to br_date or payment_date
    date_priority = ["order_date", "br_date", "payment_date"]
    merged["fiscal_year"] = ""
    for date_col in date_priority:
        if date_col in merged.columns:
            mask = merged["fiscal_year"].isin(["", None])
            merged.loc[mask, "fiscal_year"] = (
                merged.loc[mask, date_col].apply(derive_fiscal_year)
            )

    # Ensure output directory exists
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_path = os.path.join(PROCESSED_DIR, "all_work_orders.csv")
    merged.to_csv(out_path, index=False)
    logger.info(f"Saved {len(merged)} normalized records to {out_path}")

    # Also save as JSON for downstream scripts
    json_path = os.path.join(PROCESSED_DIR, "all_work_orders.json")
    # Convert timestamps to strings for JSON serialization
    json_df = merged.copy()
    date_cols = ["start_date", "end_date", "order_date", "payment_date",
                 "sbr_date", "br_date", "cbr_date"]
    for col in date_cols:
        if col in json_df.columns:
            json_df[col] = json_df[col].astype(str).replace("NaT", "")
    json_df.to_json(json_path, orient="records", indent=None)
    logger.info(f"Saved JSON to {json_path}")


if __name__ == "__main__":
    normalize_all()

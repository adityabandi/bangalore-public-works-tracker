"""Normalize and merge all BBMP work order CSVs into a canonical dataset."""

import glob
import hashlib
import json
import logging
import os
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


def read_csv_safe(path: str) -> pd.DataFrame | None:
    """Read a CSV with encoding fallbacks."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=encoding)
            if len(df) > 0:
                return df
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return None
    logger.warning(f"Could not read {path} with any encoding")
    return None


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

        # Normalize column names
        df.columns = [normalize_column_name(c) for c in df.columns]

        # Check for minimum required columns
        has_work = "name_of_work" in df.columns
        has_amount = "gross" in df.columns
        if not has_work and not has_amount:
            logger.warning(f"Skipping {csv_path}: missing name_of_work and gross columns")
            continue

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
    key = f"{row.get('job_number', '')}|{row.get('ward_198', '')}|{row.get('order_date', '')}|{row.get('gross', '')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate records across datasets."""
    before = len(df)

    df["_dedup_key"] = df.apply(
        lambda r: f"{r.get('job_number', '')}|{r.get('ward_198', '')}|{r.get('order_date', '')}",
        axis=1,
    )

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

    # Derive fiscal year from order_date
    if "order_date" in merged.columns:
        merged["fiscal_year"] = merged["order_date"].apply(derive_fiscal_year)
    else:
        merged["fiscal_year"] = ""

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

"""Fetch BBMP work order CSVs from OpenCity.in using CKAN API discovery."""

import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATASETS, RAW_DIR, HASHES_FILE, FETCH_STATUS_FILE
from utils.ckan_client import get_csv_resources, download_resource, load_hashes, save_hashes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Convert resource name to a safe filename."""
    name = re.sub(r"[^\w\s\-.]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:200] if name else "unnamed"


def detect_ward_regime(resource_name: str) -> int | None:
    """Detect ward regime from resource filename for mixed-regime datasets."""
    name_lower = resource_name.lower()
    if "198" in name_lower:
        return 198
    if "225" in name_lower:
        return 225
    if "243" in name_lower:
        return 243
    return None


def fetch_all():
    """Download all configured datasets. Returns True if any data changed."""
    old_hashes = load_hashes(HASHES_FILE)
    new_hashes = {}
    changed = False
    total_downloaded = 0
    total_skipped = 0

    for dataset_key, config in sorted(DATASETS.items(), key=lambda x: x[1]["priority"]):
        logger.info(f"Fetching dataset: {dataset_key} ({config['description']})")
        dest_dir = os.path.join(RAW_DIR, dataset_key)

        try:
            resources = get_csv_resources(config["package_id"])
            logger.info(f"  Found {len(resources)} CSV resources")
        except Exception as e:
            logger.error(f"  Failed to fetch package {config['package_id']}: {e}")
            # Preserve old hashes for this dataset so we don't lose track
            for k, v in old_hashes.items():
                if k.startswith(f"{dataset_key}/"):
                    new_hashes[k] = v
            continue

        for resource in resources:
            fname = sanitize_filename(resource["name"]) + ".csv"
            dest_path = os.path.join(dest_dir, fname)
            hash_key = f"{dataset_key}/{resource['id']}"

            try:
                file_hash = download_resource(resource["url"], dest_path)
                new_hashes[hash_key] = file_hash

                if old_hashes.get(hash_key) != file_hash:
                    changed = True
                    logger.info(f"  Changed: {fname}")
                    total_downloaded += 1
                else:
                    total_skipped += 1
            except Exception as e:
                logger.error(f"  Failed to download {resource['name']}: {e}")
                # Preserve old hash
                if hash_key in old_hashes:
                    new_hashes[hash_key] = old_hashes[hash_key]

    save_hashes(HASHES_FILE, new_hashes)

    # Write status file for GitHub Actions conditional
    os.makedirs(os.path.dirname(FETCH_STATUS_FILE), exist_ok=True)
    with open(FETCH_STATUS_FILE, "w") as f:
        json.dump({
            "changed": changed,
            "downloaded": total_downloaded,
            "skipped": total_skipped,
            "total_resources": total_downloaded + total_skipped,
        }, f, indent=2)

    logger.info(
        f"Fetch complete: {total_downloaded} changed, {total_skipped} unchanged, "
        f"data_changed={changed}"
    )
    return changed


if __name__ == "__main__":
    fetch_all()

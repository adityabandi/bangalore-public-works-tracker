"""Lightweight CKAN API client for OpenCity.in data discovery and download."""

import hashlib
import json
import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://data.opencity.in/api/3/action"
REQUEST_DELAY = 1.0  # seconds between requests (be respectful)
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


def get_package(package_id: str) -> dict:
    """Fetch dataset metadata including all resource URLs."""
    url = f"{BASE_URL}/package_show"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params={"id": package_id}, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            if not result.get("success"):
                raise ValueError(f"CKAN API returned success=false for {package_id}")
            return result["result"]
        except (requests.RequestException, ValueError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                logger.warning(f"Retry {attempt + 1} for {package_id} after {wait}s: {e}")
                time.sleep(wait)
            else:
                raise
    return {}


def get_csv_resources(package_id: str) -> list[dict]:
    """Get all CSV resources from a dataset package."""
    pkg = get_package(package_id)
    resources = []
    for r in pkg.get("resources", []):
        fmt = (r.get("format") or "").upper()
        if fmt in ("CSV", "XLS", "XLSX"):
            resources.append({
                "id": r["id"],
                "name": r.get("name", ""),
                "url": r["url"],
                "format": fmt,
                "size": r.get("size"),
                "last_modified": r.get("last_modified"),
            })
    return resources


def download_resource(url: str, dest_path: str) -> str:
    """Download a resource file and return its SHA256 hash.

    Streams the download to handle large files efficiently.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()

            sha256 = hashlib.sha256()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    sha256.update(chunk)

            time.sleep(REQUEST_DELAY)
            return sha256.hexdigest()
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                logger.warning(f"Retry download {attempt + 1} for {url}: {e}")
                time.sleep(wait)
            else:
                raise

    return ""


def load_hashes(path: str) -> dict:
    """Load previous file hashes from JSON."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_hashes(path: str, hashes: dict):
    """Save file hashes to JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(hashes, f, indent=2)

"""Normalize ward numbers across BBMP's 198/225/243 ward regimes."""

import json
import os
import re
import logging

logger = logging.getLogger(__name__)

BENCHMARKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "benchmarks")


class WardMapper:
    def __init__(self, mapping_file: str | None = None):
        if mapping_file is None:
            mapping_file = os.path.join(BENCHMARKS_DIR, "ward_mapping.json")

        if os.path.exists(mapping_file):
            with open(mapping_file) as f:
                self.mapping = json.load(f)
        else:
            logger.warning(f"Ward mapping file not found: {mapping_file}")
            self.mapping = {}

        self._name_to_198 = {}
        for num, name in self.mapping.get("ward_198_to_name", {}).items():
            self._name_to_198[name.lower().strip()] = int(num)

    def normalize_ward(self, ward_value, source_regime: int = 198) -> dict:
        """Convert any ward reference to a standardized format.

        ward_value could be: 42, "42", "Malleshwaram", "Ward-42",
                            "42 - Malleshwaram", "Ward No. 42"

        Returns dict with ward_198, ward_name, zone keys.
        """
        result = {
            "ward_198": None,
            "ward_name": None,
            "zone": None,
        }

        if ward_value is None:
            return result

        s = str(ward_value).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return result

        ward_num = self._extract_number(s)

        if ward_num is not None:
            if source_regime == 198:
                result["ward_198"] = ward_num
            elif source_regime == 225:
                mapped = self.mapping.get("ward_225_to_198", {}).get(str(ward_num))
                if mapped:
                    result["ward_198"] = mapped[0] if isinstance(mapped, list) else mapped
            elif source_regime == 243:
                mapped = self.mapping.get("ward_243_to_198", {}).get(str(ward_num))
                if mapped:
                    result["ward_198"] = mapped[0] if isinstance(mapped, list) else mapped

        # Try name lookup if no number found
        if result["ward_198"] is None:
            name_part = re.sub(r"^\d+\s*[-–]\s*", "", s).strip().lower()
            if name_part in self._name_to_198:
                result["ward_198"] = self._name_to_198[name_part]

        # Fill in name and zone from mapping
        if result["ward_198"] is not None:
            ward_key = str(result["ward_198"])
            result["ward_name"] = self.mapping.get("ward_198_to_name", {}).get(ward_key)
            result["zone"] = self.mapping.get("ward_198_to_zone", {}).get(ward_key)

        return result

    def _extract_number(self, s: str) -> int | None:
        """Extract a ward number from various formats."""
        # Direct number
        try:
            n = int(float(s))
            if 1 <= n <= 300:
                return n
        except (ValueError, OverflowError):
            pass

        # "Ward-42", "Ward No. 42", "Ward 42"
        m = re.search(r"ward\s*(?:no\.?\s*)?(\d+)", s, re.IGNORECASE)
        if m:
            return int(m.group(1))

        # "42 - Malleshwaram" or "42-Malleshwaram"
        m = re.match(r"(\d+)\s*[-–]", s)
        if m:
            return int(m.group(1))

        # Leading number like "42 Some Ward Name"
        m = re.match(r"(\d+)\s+\w", s)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 300:
                return n

        return None

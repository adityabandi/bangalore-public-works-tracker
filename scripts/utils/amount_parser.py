"""Parse Indian currency amounts from various formats."""

import re
import math


def parse_indian_amount(value) -> float:
    """Parse Indian formatted currency amounts to float.

    Handles:
    - "12,34,567.89" -> 1234567.89  (Indian comma format)
    - "1234567.89"   -> 1234567.89  (plain number)
    - "Rs. 12345"    -> 12345.0     (Rs. prefix)
    - ""  / None     -> 0.0         (missing data)
    - "12,34,567"    -> 1234567.0   (no decimal)
    """
    if value is None:
        return 0.0

    s = str(value).strip()

    if s in ("", "nan", "None", "NaN", "-", "NA", "N/A", "null"):
        return 0.0

    # Strip currency prefixes
    s = re.sub(r"^Rs\.?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^INR\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^₹\s*", "", s)

    # Remove commas (Indian or international format)
    s = s.replace(",", "").strip()

    # Remove trailing non-numeric chars like "/-"
    s = re.sub(r"[/\-]+$", "", s).strip()

    if not s:
        return 0.0

    try:
        result = float(s)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except (ValueError, OverflowError):
        return 0.0


def format_lakhs(amount: float) -> str:
    """Format amount in lakhs for display. E.g., 1234567 -> '12.35 L'."""
    if amount >= 1e7:
        return f"{amount / 1e7:.2f} Cr"
    if amount >= 1e5:
        return f"{amount / 1e5:.2f} L"
    if amount >= 1e3:
        return f"{amount / 1e3:.1f} K"
    return f"{amount:.0f}"

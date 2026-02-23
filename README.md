# Bangalore Public Works Tracker

Automated anomaly detection in BBMP (Bruhat Bengaluru Mahanagara Palike) public works spending.

## What This Does

This system ingests publicly available BBMP work order data, runs statistical anomaly detection, and surfaces suspicious patterns through a web dashboard. It runs entirely on GitHub — Actions for compute, Pages for hosting — at **zero cost**.

### Anomaly Detection Heuristics

1. **Cost Outliers** — Flags work orders significantly above the ward/category median (IQR-based)
2. **Contractor Concentration** — Flags contractors winning >15% of orders in a ward
3. **Duplicate Works** — Flags near-identical work descriptions in the same ward within 12 months
4. **Payment Speed** — Flags suspiciously fast order-to-payment turnarounds
5. **Deduction Ratio** — Flags unusual gross-to-net deduction patterns
6. **Benford's Law** — Chi-squared test on first-digit distribution of spending amounts per ward

### Data Sources

- **BBMP Work Orders**: [OpenCity.in](https://data.opencity.in) — CSV downloads covering 2013-2025
- **Ward Boundaries**: [DataMeet Municipal Spatial Data](https://github.com/datameet/Municipal_Spatial_Data)
- **Cost Benchmarks**: Karnataka PWD Schedule of Rates 2024-25

## Architecture

```
GitHub Actions (daily cron) → Python scripts → JSON files → git commit → GitHub Pages
```

No database. No server. Precomputed JSON files are the "API."

## Running Locally

```bash
pip install -r requirements.txt

# Fetch data from OpenCity.in
python scripts/fetch_data.py

# Normalize and merge all CSVs
python scripts/normalize.py

# Run anomaly detection
python scripts/detect_anomalies.py

# Generate dashboard JSON
python scripts/generate_site_data.py

# Copy to docs and open dashboard
cp data/site/*.json docs/data/
open docs/index.html
```

## Disclaimer

This tool flags **statistical anomalies** for further investigation. Flagged items are not accusations of wrongdoing. Always verify findings through independent sources before drawing conclusions.

## License

MIT

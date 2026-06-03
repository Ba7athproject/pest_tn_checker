# -*- coding: utf-8 -*-
"""
scripts/01_download_db.py
CLI script to download the official EU active substances database.
"""
import os
import sys
import json
import argparse
import time
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Adjust path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common import config

API_BASE = "https://api.datalake.sante.service.ec.europa.eu"
API_VERSION = "v3.0"
DEFAULT_URL = f"{API_BASE}/sante/pesticides/active-substances-download?format=json&api-version={API_VERSION}"
USER_AGENT = "tn-pesticides-reconciliation/2.0"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 5
BACKOFF_FACTOR = 1.5

def build_session() -> requests.Session:
    retry = Retry(
        total=MAX_RETRIES,
        read=MAX_RETRIES,
        connect=MAX_RETRIES,
        status=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    })
    return s

def extract_records(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ["value", "data", "results", "items", "content", "records"]:
            if key in payload and isinstance(payload[key], list):
                return payload[key]
    return []

def main():
    parser = argparse.ArgumentParser(description="Download the EU active substances database.")
    parser.add_argument(
        "--output-csv",
        default=config.REFERENCE_CSV,
        help=f"Path to save output CSV (default: {config.REFERENCE_CSV})"
    )
    parser.add_argument(
        "--output-json",
        default=os.path.join(config.REFERENCE_DIR, "eu_active_substances_full.json"),
        help="Path to save raw output JSON"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="API URL to download data from"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force redownload even if output files already exist"
    )
    args = parser.parse_args()

    # Check if files exist and --force is not specified
    if not args.force and os.path.exists(args.output_csv) and os.path.exists(args.output_json):
        print(f"[INFO] Reference files already exist at {args.output_csv}. Use --force to redownload.")
        return

    print(f"Connecting to EU database API: {args.url}")
    session = build_session()
    
    try:
        resp = session.get(args.url, timeout=REQUEST_TIMEOUT)
        if resp.status_code >= 400:
            print(f"[ERROR] Download failed (HTTP {resp.status_code}): {resp.text[:300]}")
            sys.exit(1)
            
        # Parse payload
        try:
            payload = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
        except Exception:
            try:
                payload = resp.json()
            except Exception as e:
                print(f"[ERROR] Failed to parse payload as NDJSON or standard JSON: {e}")
                sys.exit(1)

        # Write raw json
        os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Saved raw JSON payload to: {args.output_json}")

        records = extract_records(payload)
        if not records:
            print("[ERROR] No substance records found in downloaded payload.")
            sys.exit(1)

        os.makedirs(os.path.dirname(args.output_csv), exist_ok=True)
        pd.DataFrame(records).to_csv(args.output_csv, index=False, encoding="utf-8-sig")
        print(f"Saved {len(records)} active substances to CSV: {args.output_csv}")

    except requests.RequestException as e:
        print(f"[ERROR] Network request failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

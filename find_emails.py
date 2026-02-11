#!/usr/bin/env python3
"""
Find recruiter emails from startups (AngelList/Wellfound + LinkedIn).
Output: recruiters.csv (skips companies already in sent_emails.json).
Requires: YOU_API_KEY or BRAVE_API_KEY in .env
"""
import sys
import os
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT / "email_finder")
sys.path.insert(0, str(ROOT / "email_finder"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from find_startups import find_startups_and_recruiters

OUTPUT_CSV = ROOT / "recruiters.csv"
SENT_JSON = ROOT / "email_outreach" / "sent_emails.json"


def _load_excluded_companies():
    if not SENT_JSON.exists():
        return set()
    try:
        with open(SENT_JSON) as f:
            data = json.load(f)
        return {e.get("company", "").strip() for e in data.get("sent", []) if e.get("company")}
    except Exception:
        return set()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Find startup recruiter emails (AngelList/Wellfound)")
    p.add_argument("--query", "-q", default="AI startup internship", help="Search query")
    p.add_argument("--max", "-m", type=int, default=50, help="Max startups to find")
    p.add_argument("--output", "-o", default=str(OUTPUT_CSV), help="Output CSV path")
    args = p.parse_args()
    out = Path(args.output)
    if not out.is_absolute():
        out = ROOT / out
    exclude = _load_excluded_companies()
    find_startups_and_recruiters(
        query=args.query,
        max_startups=args.max,
        output_csv=str(out),
        exclude_companies=exclude,
    )

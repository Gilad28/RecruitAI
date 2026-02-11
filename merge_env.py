#!/usr/bin/env python3
"""One-time: merge email_finder/.env and email_outreach/.env into root .env."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sources = [ROOT / "email_finder" / ".env", ROOT / "email_outreach" / ".env"]
dest = ROOT / ".env"

merged = {}
if dest.exists():
    for line in dest.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            merged[k.strip()] = v.strip()
for p in sources:
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                merged[k.strip()] = v.strip()

if merged:
    lines = [f"{k}={v}" for k, v in merged.items()]
    dest.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(merged)} vars to {dest}")
    print("You can now delete email_finder/.env and email_outreach/.env")
else:
    print("No vars found in subfolder .env files")

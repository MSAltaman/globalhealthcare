"""Create an empty country profile with every required section.

  python scripts/new_profile.py JPN Japan --wave 0

Fails if the profile already exists.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ["overview", "financing", "covered", "cost_sharing", "additional_care", "access",
            "outcomes", "costs", "what_works", "problems", "reforms", "us_lessons"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("iso3")
    ap.add_argument("name")
    ap.add_argument("--wave", type=int, default=1)
    args = ap.parse_args()

    iso3 = args.iso3.upper()
    path = ROOT / "data" / "countries" / f"{iso3}.json"
    if path.exists():
        raise SystemExit(f"{path} already exists.")
    today = dt.date.today().isoformat()
    profile = {
        "iso3": iso3,
        "name": args.name,
        "wave": args.wave,
        "system_as_of": today,
        "status": "draft",
        "model": {"type": "mixed", "label": "TODO: plain-language name of the model"},
        "universal_coverage": {"legal_basis_claim_ids": [], "meets_definition": True},
        "sections": {s: [] for s in SECTIONS},
        "indicators_file": f"data/indicators/{iso3}.json",
        "sources": [],
        "rankings": [],
        "changelog": [{"date": today, "note": "Profile created."}],
    }
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Created {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

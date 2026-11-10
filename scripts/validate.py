"""Validate every country profile against the schema plus integrity rules.

  python scripts/validate.py

Rules beyond the JSON schema:
  - claim ids are unique and match <ISO3>-<section>-<nnn>
  - every claim's source_id exists in the profile's sources
  - every source is used by at least one claim or ranking (warning)
  - tier-4 sources may not be the only support for a claim (error)
  - us_lessons claims must come from tier 1-3 sources
  - claims about current conditions must rest on data from the last
    MAX_DATA_AGE years (data_year, else the source's publication year);
    older data is allowed only on claims marked "historical": true
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import datetime as dt
import re

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "country.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
MAX_DATA_AGE = 10


def latest_data_year(claim: dict, source: dict) -> int:
    d = claim.get("data_year")
    years = [int(y) for y in re.findall(r"(?:19|20)\d\d", str(d))] if d is not None else []
    return max(years) if years else source["year"]


def check_profile(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    profile = json.loads(path.read_text(encoding="utf-8"))

    for err in sorted(VALIDATOR.iter_errors(profile), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"schema {loc}: {err.message}")
    if errors:
        return errors, warnings

    iso3 = profile["iso3"]
    if path.stem != iso3:
        errors.append(f"file name {path.name} does not match iso3 {iso3}")

    sources = {s["id"]: s for s in profile["sources"]}
    used: set[str] = set()
    seen: set[str] = set()

    for section, claims in profile["sections"].items():
        for c in claims:
            cid = c["id"]
            if cid in seen:
                errors.append(f"duplicate claim id {cid}")
            seen.add(cid)
            if not cid.startswith(f"{iso3}-{section}-"):
                errors.append(f"{cid}: id must start with {iso3}-{section}-")
            sid = c["source_id"]
            if sid not in sources:
                errors.append(f"{cid}: unknown source_id {sid}")
                continue
            used.add(sid)
            tier = sources[sid]["tier"]
            if tier == 4:
                errors.append(f"{cid}: tier-4 source {sid} cannot be the sole support")
            if section == "us_lessons" and tier > 3:
                errors.append(f"{cid}: us_lessons needs a tier 1-3 source")
            year = latest_data_year(c, sources[sid])
            if year < dt.date.today().year - MAX_DATA_AGE and not c.get("historical"):
                errors.append(f"{cid}: data from {year} is older than {MAX_DATA_AGE} years; "
                              "find current data, or mark historical if the claim states a past event")

    for r in profile.get("rankings", []):
        if r["source_id"] not in sources:
            errors.append(f"ranking {r['study']}: unknown source_id {r['source_id']}")
        used.add(r["source_id"])

    for sid in sources:
        if sid not in used:
            warnings.append(f"source {sid} is not cited by any claim")

    return errors, warnings


def main() -> int:
    files = sorted((ROOT / "data" / "countries").glob("*.json"))
    if not files:
        print("No country profiles found.")
        return 0
    bad = False
    for f in files:
        errors, warnings = check_profile(f)
        status = "OK" if not errors else "INVALID"
        print(f"{f.name}: {status}")
        for e in errors:
            print(f"  ERROR {e}")
        for w in warnings:
            print(f"  warn  {w}")
        bad |= bool(errors)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

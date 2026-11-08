"""Code check for every claim: is its fingerprinted passage still in the source?

For each claim that has char_start / char_end / passage_sha256, loads the
cached normalized source (fetching it if needed) and recomputes the hash.

  python scripts/verify_claims.py              # all countries, update files
  python scripts/verify_claims.py DEU JPN      # selected countries
  python scripts/verify_claims.py --check      # CI mode: no writes, no fetching;
                                               # fails if any claim is marked 'fail'

Claims without a fingerprint stay 'pending'. The 'supports' check (does the
passage actually support the statement?) is done by a model and recorded
separately; this script never sets it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sourcetext  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COUNTRIES = ROOT / "data" / "countries"


COPY_RUN_WORDS = 12  # a statement sharing this many consecutive words with its source is flagged


def copied_run(statement: str, source_text: str, n: int = COPY_RUN_WORDS) -> str | None:
    """Return the first n-word run the statement shares verbatim with the source, if any."""
    words = sourcetext.normalize(statement).lower().split()
    haystack = source_text.lower()
    for i in range(len(words) - n + 1):
        run = " ".join(words[i:i + n])
        if run in haystack:
            return run
    return None


def iter_claims(profile: dict):
    for section, claims in profile.get("sections", {}).items():
        for claim in claims:
            yield section, claim


def verify_profile(profile: dict, fetch_missing: bool, today: str) -> dict:
    sources = {s["id"]: s for s in profile.get("sources", [])}
    texts: dict[str, str | None] = {}
    counts = {"pass": 0, "fail": 0, "pending": 0}

    for _, claim in iter_claims(profile):
        loc = claim.get("locator", {})
        ver = claim.setdefault("verification", {"passage_found": "pending", "supports": "pending"})
        if not all(k in loc for k in ("char_start", "char_end", "passage_sha256")):
            ver["passage_found"] = "pending"
            counts["pending"] += 1
            continue

        sid = claim["source_id"]
        if sid not in texts:
            text = sourcetext.load(sid)
            if text is None and fetch_missing and sid in sources:
                try:
                    text = sourcetext.fetch(sid, sources[sid].get("text_url") or sources[sid]["url"])
                except Exception as e:  # network, 404, parse error
                    print(f"  ! could not fetch {sid}: {e}", file=sys.stderr)
            texts[sid] = text

        text = texts[sid]
        if text is None:
            ver["passage_found"] = "pending"
            ver["note"] = "Source text unavailable for checking."
            counts["pending"] += 1
            continue

        ok = sourcetext.check(text, loc["char_start"], loc["char_end"], loc["passage_sha256"])
        ver["passage_found"] = "pass" if ok else "fail"
        ver["checked_on"] = today
        if not ok:
            ver["note"] = "Passage missing or changed in current source; re-extract."
        elif copied_run(claim["statement"], text):
            ver["passage_found"] = "fail"
            ver["note"] = f"Statement copies {COPY_RUN_WORDS}+ consecutive words from the source; rewrite in own words."
        else:
            ver.pop("note", None)
        counts[ver["passage_found"]] += 1

    # Roll up status.
    all_claims = [c for _, c in iter_claims(profile)]
    if any(c["verification"]["passage_found"] == "fail" or c["verification"]["supports"] == "fail" for c in all_claims):
        profile["status"] = "needs_review"
    elif all_claims and all(
        c["verification"]["passage_found"] == "pass" and c["verification"]["supports"] == "pass" for c in all_claims
    ):
        profile["status"] = "verified"
    else:
        profile["status"] = "draft"
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("countries", nargs="*", help="ISO3 codes; default all")
    ap.add_argument("--check", action="store_true", help="CI mode: no writes, no fetching")
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    files = sorted(COUNTRIES.glob("*.json"))
    if args.countries:
        wanted = {c.upper() for c in args.countries}
        files = [f for f in files if f.stem in wanted]

    failed = False
    for f in files:
        profile = json.loads(f.read_text(encoding="utf-8"))
        if args.check:
            fails = [c["id"] for _, c in iter_claims(profile)
                     if "fail" in (c["verification"]["passage_found"], c["verification"]["supports"])]
            pending = sum(1 for _, c in iter_claims(profile)
                          if "pending" in (c["verification"]["passage_found"], c["verification"]["supports"]))
            print(f"{f.stem}: status={profile['status']} failed={len(fails)} pending={pending}")
            if fails:
                failed = True
                for cid in fails:
                    print(f"  FAIL {cid}")
            continue

        counts = verify_profile(profile, fetch_missing=True, today=today)
        f.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{f.stem}: passage pass={counts['pass']} fail={counts['fail']} pending={counts['pending']} -> {profile['status']}")
        failed |= counts["fail"] > 0

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

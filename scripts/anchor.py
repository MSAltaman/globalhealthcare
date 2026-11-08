"""Anchor a claim to its supporting passage, using a start and an end phrase.

The passage is taken from the cached normalized source text, from the first
occurrence of --start through the first occurrence of --end after it. Typing
only the two ends avoids transcription errors in long passages. The page is
filled in from the PDF's page markers when available.

  python scripts/anchor.py DEU DEU-access-001 --start "According to the EU" --end "(3.6 %)."
  python scripts/anchor.py DEU DEU-access-001 --start ... --end ... --show   # preview only

Writes char_start, char_end, passage_sha256 and page into the claim's locator
and resets verification.passage_found to 'pending' (run verify_claims.py next).
The passage itself is printed for your review and never written to the repo.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sourcetext  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def find_claim(profile: dict, claim_id: str) -> dict:
    for claims in profile["sections"].values():
        for c in claims:
            if c["id"] == claim_id:
                return c
    raise SystemExit(f"Claim {claim_id} not found.")


def pdf_page(text: str, pos: int) -> int | None:
    pages = [int(m.group(1)) for m in re.finditer(r"\[\[page (\d+)\]\]", text) if m.start() <= pos]
    return pages[-1] if pages else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("iso3")
    ap.add_argument("claim_id")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--show", action="store_true", help="print the passage, change nothing")
    args = ap.parse_args()

    path = ROOT / "data" / "countries" / f"{args.iso3.upper()}.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    claim = find_claim(profile, args.claim_id)
    text = sourcetext.load(claim["source_id"])
    if text is None:
        raise SystemExit(f"No cached text for {claim['source_id']}; run sourcetext.py fetch first.")

    start = sourcetext.normalize(args.start)
    end = sourcetext.normalize(args.end)
    i = text.find(start)
    if i < 0:
        raise SystemExit("Start phrase not found in source text.")
    j = text.find(end, i)
    if j < 0:
        raise SystemExit("End phrase not found after the start phrase.")
    passage = text[i:j + len(end)]
    if len(passage) > 1500:
        raise SystemExit(f"Passage is {len(passage)} characters; anchor a tighter span (max 1500).")
    anchor = sourcetext.locate(text, passage)

    print(f"PASSAGE ({len(passage)} chars):\n{passage}\n")
    print(f"CLAIM:\n{claim['statement']}")
    if args.show:
        return 0

    loc = {k: v for k, v in claim.get("locator", {}).items()
           if k in ("page", "section", "table", "figure")}
    page = pdf_page(text, anchor["char_start"])
    if page is not None:
        loc["page"] = page
    if not any(k in loc for k in ("page", "section", "table", "figure")):
        loc["section"] = "Full text"
    loc.update(anchor)
    claim["locator"] = loc
    claim.setdefault("verification", {})
    claim["verification"]["passage_found"] = "pending"
    claim["verification"].setdefault("supports", "pending")
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nAnchored {args.claim_id} (page {loc.get('page', '-')}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

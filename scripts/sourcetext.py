"""Fetch, normalize and fingerprint source documents.

The repo never stores text copied from sources. Instead, a claim stores:
  - char_start / char_end: offsets into the *normalized* source text
  - passage_sha256: SHA-256 of that normalized passage

Anyone can re-fetch the source, normalize it the same way, and confirm the
passage is still there and unchanged. Cached source text lives in .cache/
(gitignored) and is never committed.

CLI:
  python scripts/sourcetext.py fetch <source_id> <url>
  python scripts/sourcetext.py locate <source_id> < passage.txt
      -> prints {"char_start": .., "char_end": .., "passage_sha256": ".."}
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "sources"

USER_AGENT = "GlobalHealthcareAtlas/0.1 (research; +https://github.com/MSAltaman/globalheathcare)"

_REPLACEMENTS = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", "­": "",  # nbsp, soft hyphen
}


def normalize(text: str) -> str:
    """Make text comparable across HTML/PDF extraction quirks.

    NFKC (splits ligatures like 'ﬁ'), straightens quotes and dashes, joins
    words hyphenated across line breaks, and collapses all whitespace runs to
    a single space. Case is preserved.
    """
    text = unicodedata.normalize("NFKC", text)
    for a, b in _REPLACEMENTS.items():
        text = text.replace(a, b)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def extract_text(content: bytes, content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    if "pdf" in ct or url.lower().endswith(".pdf") or content[:5] == b"%PDF-":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        # Page markers let locators cite pages; they are part of normalized text.
        parts = [f"[[page {i}]] {p.extract_text() or ''}" for i, p in enumerate(reader.pages, start=1)]
        return "\n".join(parts)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
        tag.decompose()
    return soup.get_text(" ")


def cache_path(source_id: str) -> Path:
    return CACHE / f"{source_id}.txt"


def fetch(source_id: str, url: str, timeout: int = 60) -> str:
    """Download a source, normalize it, cache it. Returns normalized text."""
    import requests

    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    text = normalize(extract_text(resp.content, resp.headers.get("content-type", ""), url))
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path(source_id).write_text(text, encoding="utf-8")
    return text


def load(source_id: str) -> str | None:
    p = cache_path(source_id)
    return p.read_text(encoding="utf-8") if p.exists() else None


def locate(source_text: str, passage: str) -> dict:
    """Find a passage in normalized source text and fingerprint it.

    Raises ValueError if the passage is absent or ambiguous, so a claim can
    never be anchored to text the source does not contain.
    """
    needle = normalize(passage)
    if len(needle) < 20:
        raise ValueError("Passage too short to anchor reliably (min 20 characters).")
    start = source_text.find(needle)
    if start < 0:
        raise ValueError("Passage not found in source text.")
    if source_text.find(needle, start + 1) >= 0:
        raise ValueError("Passage occurs more than once; extend it so it is unique.")
    end = start + len(needle)
    return {"char_start": start, "char_end": end, "passage_sha256": sha256(needle)}


def check(source_text: str, char_start: int, char_end: int, passage_sha256: str) -> bool:
    """True if the fingerprinted passage is present, unchanged, at its offsets."""
    if char_end > len(source_text) or char_start >= char_end:
        return False
    return sha256(source_text[char_start:char_end]) == passage_sha256


def _main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "fetch":
        text = fetch(argv[1], argv[2])
        print(json.dumps({"source_id": argv[1], "chars": len(text), "content_sha256": sha256(text)}))
        return 0
    if len(argv) == 2 and argv[0] == "locate":
        text = load(argv[1])
        if text is None:
            print(f"No cached text for {argv[1]}; run fetch first.", file=sys.stderr)
            return 2
        try:
            print(json.dumps(locate(text, sys.stdin.read())))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

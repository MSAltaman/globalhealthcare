import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_indicators  # noqa: E402
import sourcetext  # noqa: E402
import verify_claims  # noqa: E402

SAMPLE = """<html><head><script>x()</script></head><body>
<p>The statutory system covers roughly 90 per­cent of the popu-
lation through competing sickness funds.</p><p>Co‑payments are capped at 2% of income.</p>
</body></html>"""


def test_normalize_handles_html_quirks():
    text = sourcetext.normalize(sourcetext.extract_text(SAMPLE.encode(), "text/html", "x.html"))
    assert "x()" not in text
    assert "90 percent of the population" in text
    assert "  " not in text


def test_locate_and_check_roundtrip():
    text = sourcetext.normalize(sourcetext.extract_text(SAMPLE.encode(), "text/html", "x.html"))
    anchor = sourcetext.locate(text, "covers roughly 90 percent of the population")
    assert sourcetext.check(text, anchor["char_start"], anchor["char_end"], anchor["passage_sha256"])
    changed = text.replace("90", "80")
    assert not sourcetext.check(changed, anchor["char_start"], anchor["char_end"], anchor["passage_sha256"])


def test_locate_rejects_absent_and_short():
    text = sourcetext.normalize("Some source text that is long enough to search through.")
    for bad in ("not in the source at all, really", "short"):
        try:
            sourcetext.locate(text, bad)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_world_bank_latest_value_skips_nulls():
    payload = [
        {"page": 1, "pages": 1, "per_page": 100, "total": 3},
        [
            {"date": "2024", "value": None},
            {"date": "2023", "value": 12.3},
            {"date": "2021", "value": 11.9},
        ],
    ]
    assert fetch_indicators.latest_value(payload) == {"value": 12.3, "year": 2023}
    assert fetch_indicators.latest_value([{"message": "error"}]) is None


def test_verify_profile_rolls_up_status(tmp_path, monkeypatch):
    text = sourcetext.normalize("Every resident must hold health insurance under federal law since 2009.")
    anchor = sourcetext.locate(text, "Every resident must hold health insurance")
    monkeypatch.setattr(sourcetext, "load", lambda sid: text)
    claim = {
        "id": "DEU-overview-001",
        "statement": "Health insurance has been mandatory for all residents since 2009.",
        "source_id": "src",
        "locator": {"section": "1", **anchor},
        "verification": {"passage_found": "pending", "supports": "pass"},
    }
    profile = {"status": "draft", "sources": [{"id": "src", "url": "https://example.org"}],
               "sections": {"overview": [claim]}}
    counts = verify_claims.verify_profile(profile, fetch_missing=False, today="2026-11-08")
    assert counts["pass"] == 1
    assert profile["status"] == "verified"


def test_copied_run_detects_verbatim_statements():
    src = sourcetext.normalize("The statutory system covers roughly ninety percent of the population through many competing sickness funds across the country today.")
    copied = "The statutory system covers roughly ninety percent of the population through many competing sickness funds."
    own = "About nine in ten residents are insured through one of many competing public sickness funds."
    assert verify_claims.copied_run(copied, src) is not None
    assert verify_claims.copied_run(own, src) is None


def test_gho_latest_uses_whole_population_rows():
    payload = {"value": [
        {"TimeDim": 2021, "NumericValue": 5.0, "Dim1": "RESIDENCEAREATYPE_URB"},
        {"TimeDim": 2019, "NumericValue": 4.0, "Dim1": "RESIDENCEAREATYPE_TOTL"},
        {"TimeDim": 2020, "NumericValue": None, "Dim1": None},
    ]}
    assert fetch_indicators.gho_latest(payload) == {"value": 4.0, "year": 2019}

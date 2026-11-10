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


def test_oecd_latest_applies_filters_and_takes_newest():
    rows = [
        {"REF_AREA": "USA", "TIME_PERIOD": "2022", "OBS_VALUE": "90.1", "Sex": "Total"},
        {"REF_AREA": "USA", "TIME_PERIOD": "2024", "OBS_VALUE": "91.8", "Sex": "Total"},
        {"REF_AREA": "USA", "TIME_PERIOD": "2025", "OBS_VALUE": "50.0", "Sex": "Male"},
        {"REF_AREA": "CAN", "TIME_PERIOD": "2025", "OBS_VALUE": "100", "Sex": "Total"},
    ]
    assert fetch_indicators.oecd_latest(rows, "USA", {"Sex": "Total"}) == {"value": 91.8, "year": 2024}
    assert fetch_indicators.oecd_latest(rows, "MEX", {"Sex": "Total"}) is None


import score  # noqa: E402


def test_normalise_orients_and_rescales():
    out = score.normalise({"A": 10, "B": 20, "C": 30}, "lower", log=False)
    assert out == {"A": 100.0, "B": 50.0, "C": 0.0}


def test_compute_drops_stale_data_and_ranks(monkeypatch):
    import datetime as dt
    cfg = {"max_data_age_years": 10, "min_indicator_share_per_domain": 0.5, "min_domains_for_overall": 1,
           "sensitivity": {"samples": 50, "seed": 1},
           "domains": [{"id": "d", "label": "D", "weight": 1, "question": "?",
                        "indicators": [{"id": "x", "better": "higher"}]}]}
    monkeypatch.setattr(score, "CFG", cfg)
    data = {"A": {"x": {"value": 5, "year": 2024}}, "B": {"x": {"value": 9, "year": 2024}},
            "C": {"x": {"value": 99, "year": 2001}}}
    res = score.compute(data, ["A", "B", "C"], today=dt.date(2026, 1, 1))
    ranks = {r["iso3"]: r["rank"] for r in res["rows"]}
    assert ranks == {"B": 1, "A": 2, "C": None}


def test_latest_data_year_prefers_data_year_range_end():
    import validate
    assert validate.latest_data_year({"data_year": "2013-2016"}, {"year": 2019}) == 2016
    assert validate.latest_data_year({}, {"year": 2009}) == 2009

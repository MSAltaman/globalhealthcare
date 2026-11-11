"""Pull comparable indicators straight from the World Bank, WHO GHO and OECD APIs.

No model ever writes these numbers. For each country and indicator the script
keeps the most recent non-empty value, its year, the API URL it came from, and
the original source organization (e.g. WHO Global Health Expenditure Database).

  python scripts/fetch_indicators.py              # every country in config/countries.json
  python scripts/fetch_indicators.py DEU JPN MEX  # selected countries

Writes data/indicators/<ISO3>.json.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "indicators.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "indicators"
API = "https://api.worldbank.org/v2"
GHO = "https://ghoapi.azureedge.net/api"
# Rows representing the whole population (not split by sex or urban/rural).
GHO_TOTAL_DIMS = {None, "SEX_BTSX", "RESIDENCEAREATYPE_TOTL", "BOTHSEXES", "TOTL"}
USER_AGENT = "GlobalHealthcareAtlas/0.1 (research; +https://github.com/MSAltaman/globalhealthcare)"

# Not covered by World Bank / WHO series.
UNSUPPORTED = {"TWN"}


def all_countries() -> list[str]:
    cfg = json.loads((ROOT / "config" / "countries.json").read_text(encoding="utf-8"))
    codes = [cfg["baseline"]["iso3"]]
    for wave in cfg["waves"]:
        codes += [c["iso3"] for c in wave["countries"]]
    return codes


def series_url(iso3: str, indicator: str, start: int, end: int) -> str:
    return f"{API}/country/{iso3}/indicator/{indicator}?format=json&date={start}:{end}&per_page=100"


def latest_value(payload: list) -> dict | None:
    """Return the most recent non-null observation from a World Bank response."""
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    rows = [r for r in payload[1] if r.get("value") is not None]
    if not rows:
        return None
    row = max(rows, key=lambda r: int(r["date"]))
    return {"value": row["value"], "year": int(row["date"])}


def gho_latest(payload: dict) -> dict | None:
    """Most recent whole-population value from a WHO GHO OData response."""
    rows = [r for r in payload.get("value", [])
            if r.get("NumericValue") is not None and r.get("Dim1") in GHO_TOTAL_DIMS]
    if not rows:
        return None
    row = max(rows, key=lambda r: int(r["TimeDim"]))
    return {"value": row["NumericValue"], "year": int(row["TimeDim"])}


OECD = "https://sdmx.oecd.org/public/rest/data"
_oecd_cache: dict[str, list[dict]] = {}


def oecd_rows(dataflow: str, start: int, session) -> list[dict]:
    """All rows of an OECD SDMX dataflow since `start`, as labelled CSV records (cached per run)."""
    if dataflow not in _oecd_cache:
        import csv
        import io
        url = f"{OECD}/{dataflow}/all?startPeriod={start}&dimensionAtObservation=AllDimensions&format=csvfilewithlabels"
        resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=180)
        resp.raise_for_status()
        _oecd_cache[dataflow] = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))
    return _oecd_cache[dataflow]


def oecd_latest(rows: list[dict], iso3: str, filters: dict) -> dict | None:
    """Most recent value for one country matching every label filter."""
    best = None
    for r in rows:
        if r.get("REF_AREA") != iso3 or not r.get("OBS_VALUE"):
            continue
        if any(r.get(k) != v for k, v in filters.items()):
            continue
        year = int(r["TIME_PERIOD"][:4])
        if best is None or year > best["year"]:
            best = {"value": float(r["OBS_VALUE"]), "year": year}
    return best


def source_org(meta_payload: list) -> str | None:
    try:
        return meta_payload[1][0].get("sourceOrganization")
    except (IndexError, TypeError, AttributeError):
        return None


def get_json(url: str, session, attempts: int = 4, timeout: int = 90):
    """GET JSON with retries on timeouts, connection errors and non-200 replies."""
    import requests

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            last = requests.HTTPError(f"{resp.status_code} for {url}")
        except (requests.Timeout, requests.ConnectionError) as e:
            last = e
        time.sleep(3 * (attempt + 1))
    raise last


def fetch_country(iso3: str, session, meta_cache: dict) -> dict:
    end = dt.date.today().year
    start = end - CONFIG["lookback_years"]
    out = {
        "iso3": iso3,
        "retrieved": dt.date.today().isoformat(),
        "provider": "World Bank WDI, WHO Global Health Observatory and OECD Health Statistics APIs",
        "indicators": [],
    }
    for ind in CONFIG["world_bank"]:
        url = series_url(iso3, ind["id"], start, end)
        latest = latest_value(get_json(url, session))
        if ind["id"] not in meta_cache:
            meta_cache[ind["id"]] = source_org(get_json(f"{API}/indicator/{ind['id']}?format=json", session))
        out["indicators"].append({
            "id": ind["id"],
            "label": ind["label"],
            "unit": ind["unit"],
            "group": ind["group"],
            "value": latest["value"] if latest else None,
            "year": latest["year"] if latest else None,
            "original_source": meta_cache[ind["id"]],
            "api_url": url,
        })
    for ind in CONFIG.get("who_gho", []):
        url = f"{GHO}/{ind['id']}?$filter=SpatialDim eq '{iso3}'"
        latest = gho_latest(get_json(url, session))
        out["indicators"].append({
            "id": ind["id"],
            "label": ind["label"],
            "unit": ind["unit"],
            "group": ind["group"],
            "value": latest["value"] if latest else None,
            "year": latest["year"] if latest else None,
            "original_source": "World Health Organization, Global Health Observatory",
            "api_url": url,
        })
    for ind in CONFIG.get("oecd", []):
        rows = oecd_rows(ind["dataflow"], start, session)
        latest = oecd_latest(rows, iso3, ind["filters"])
        out["indicators"].append({
            "id": ind["id"],
            "label": ind["label"],
            "unit": ind["unit"],
            "group": ind["group"],
            "value": latest["value"] if latest else None,
            "year": latest["year"] if latest else None,
            "original_source": "OECD Health Statistics",
            "api_url": f"{OECD}/{ind['dataflow']}/all",
        })
    return out


def main(argv: list[str]) -> int:
    import requests

    codes = [c.upper() for c in argv] or all_countries()
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    meta_cache: dict = {}
    for iso3 in codes:
        if iso3 in UNSUPPORTED:
            print(f"{iso3}: skipped (not in World Bank data; use national sources)")
            continue
        data = fetch_country(iso3, session, meta_cache)
        (OUT / f"{iso3}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        filled = sum(1 for i in data["indicators"] if i["value"] is not None)
        print(f"{iso3}: {filled}/{len(data['indicators'])} indicators")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

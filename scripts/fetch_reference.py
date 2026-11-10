"""Pull every country's latest value for each scored indicator.

The atlas scores each country against the whole world, not just the countries
it profiles. This script records, for every indicator in config/scoring.json,
the latest value (within the scoring data-age limit) for every country the
source publishes. score.py sets each indicator's 0 and 100 points from this
pool.

  python scripts/fetch_reference.py

Writes data/reference.json. Regional and income-group aggregates are excluded.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_indicators as fi  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORING = json.loads((ROOT / "config" / "scoring.json").read_text(encoding="utf-8"))
IND_CFG = json.loads((ROOT / "config" / "indicators.json").read_text(encoding="utf-8"))


def wb_countries(session) -> set[str]:
    """ISO3 codes of real countries (World Bank marks aggregates with region 'NA')."""
    data = fi.get_json(f"{fi.API}/country?format=json&per_page=400", session)
    return {c["id"] for c in data[1] if c.get("region", {}).get("id") != "NA"}


def wb_all(ind_id: str, start: int, end: int, session) -> list:
    """All countries' observations for one World Bank indicator, paged."""
    rows, page, pages = [], 1, 1
    while page <= pages:
        # mrnev=1: each country's most recent non-empty value (fast, small)
        url = f"{fi.API}/country/all/indicator/{ind_id}?format=json&mrnev=1&per_page=400&page={page}"
        for attempt in range(4):
            try:
                resp = session.get(url, headers={"User-Agent": fi.USER_AGENT}, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception:
                if attempt == 3:
                    raise
        pages = data[0]["pages"]
        rows += data[1] or []
        page += 1
    return rows


def latest_by_country(rows) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for iso3, year, value in rows:
        if value is None:
            continue
        if iso3 not in best or year > best[iso3]["year"]:
            best[iso3] = {"value": value, "year": year}
    return best


def main() -> int:
    import requests

    session = requests.Session()
    min_year = dt.date.today().year - SCORING["max_data_age_years"]
    countries = wb_countries(session)
    wanted = {i["id"] for d in SCORING["domains"] for i in d["indicators"]}
    by_source = {
        "world_bank": {i["id"]: i for i in IND_CFG["world_bank"]},
        "who_gho": {i["id"]: i for i in IND_CFG.get("who_gho", [])},
        "oecd": {i["id"]: i for i in IND_CFG.get("oecd", [])},
    }
    out = {"retrieved": dt.date.today().isoformat(), "min_year": min_year, "indicators": {}}

    for ind_id in sorted(wanted):
        rows = []
        if ind_id in by_source["world_bank"]:
            for r in wb_all(ind_id, min_year, dt.date.today().year, session):
                iso3 = r.get("countryiso3code")
                if iso3 in countries and r.get("value") is not None and int(r["date"]) >= min_year:
                    rows.append((iso3, int(r["date"]), r["value"]))
            source = "World Bank WDI"
        elif ind_id in by_source["who_gho"]:
            data = fi.get_json(f"{fi.GHO}/{ind_id}", session)
            for r in data.get("value", []):
                if (r.get("SpatialDimType") == "COUNTRY" and r.get("NumericValue") is not None
                        and r.get("Dim1") in fi.GHO_TOTAL_DIMS and int(r["TimeDim"]) >= min_year):
                    rows.append((r["SpatialDim"], int(r["TimeDim"]), r["NumericValue"]))
            source = "WHO Global Health Observatory"
        elif ind_id in by_source["oecd"]:
            cfg = by_source["oecd"][ind_id]
            for r in fi.oecd_rows(cfg["dataflow"], min_year, session):
                if not r.get("OBS_VALUE") or len(r.get("REF_AREA", "")) != 3 or r["REF_AREA"] not in countries:
                    continue
                if any(r.get(k) != v for k, v in cfg["filters"].items()):
                    continue
                rows.append((r["REF_AREA"], int(r["TIME_PERIOD"][:4]), float(r["OBS_VALUE"])))
            source = "OECD Health Statistics"
        else:
            print(f"{ind_id}: not in config/indicators.json, skipped")
            continue
        latest = latest_by_country(rows)
        out["indicators"][ind_id] = {"source": source, "countries": len(latest), "values": latest}
        print(f"{ind_id}: {len(latest)} countries")

    (ROOT / "data" / "reference.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

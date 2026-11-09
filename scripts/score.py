"""Compute the atlas's own composite ranking from data/indicators.

  python scripts/score.py

Method (all settings in config/scoring.json):
  1. For each indicator, drop values older than max_data_age_years.
  2. Orient so higher = better, optionally log-transform skewed rates, then
     rescale to 0-100 across the countries being compared (min-max).
  3. Domain score = weighted mean of its available indicators, if at least
     min_indicator_share_per_domain of the indicator weight is present.
  4. Overall score = weighted mean of available domain scores, if at least
     min_domains_for_overall domains are present; otherwise not ranked.
  5. Sensitivity: redraw domain weights at random many times and report each
     country's best and worst plausible rank (5th-95th percentile).

Scores are relative to the countries compared: adding a country can move
everyone. Writes data/scores.json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "scoring.json").read_text(encoding="utf-8"))


def load_indicators() -> dict[str, dict]:
    out = {}
    for f in sorted((ROOT / "data" / "indicators").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["iso3"]] = {i["id"]: i for i in d["indicators"]}
    return out


def names() -> dict[str, str]:
    cfg = json.loads((ROOT / "config" / "countries.json").read_text(encoding="utf-8"))
    n = {cfg["baseline"]["iso3"]: cfg["baseline"]["name"]}
    for w in cfg["waves"]:
        for c in w["countries"]:
            n[c["iso3"]] = c["name"]
    return n


def normalise(values: dict[str, float], better: str, log: bool) -> dict[str, float]:
    """Rescale to 0-100 where 100 is the best value among the countries compared."""
    xs = {k: (math.log(max(v, 1e-9)) if log else v) for k, v in values.items()}
    if better == "lower":
        xs = {k: -v for k, v in xs.items()}
    lo, hi = min(xs.values()), max(xs.values())
    if hi == lo:
        return {k: 100.0 for k in xs}
    return {k: 100 * (v - lo) / (hi - lo) for k, v in xs.items()}


def weighted_mean(pairs: list[tuple[float, float]]) -> float:
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total


def compute(data: dict[str, dict], countries: list[str], today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    min_year = today.year - CFG["max_data_age_years"]

    domain_scores: dict[str, dict[str, float]] = {c: {} for c in countries}
    detail: dict[str, dict] = {c: {} for c in countries}

    for dom in CFG["domains"]:
        total_w = sum(i.get("weight", 1) for i in dom["indicators"])
        parts: dict[str, list[tuple[float, float]]] = {c: [] for c in countries}
        for ind in dom["indicators"]:
            vals = {}
            for c in countries:
                rec = data.get(c, {}).get(ind["id"])
                if rec and rec.get("value") is not None and rec.get("year") and rec["year"] >= min_year:
                    vals[c] = rec["value"]
            if len(vals) < 2:
                continue
            norm = normalise(vals, ind["better"], ind.get("log", False))
            for c, s in norm.items():
                parts[c].append((s, ind.get("weight", 1)))
                detail[c].setdefault(dom["id"], {})[ind["id"]] = {
                    "value": vals[c], "year": data[c][ind["id"]]["year"], "score": round(s, 1)}
        for c in countries:
            present = sum(w for _, w in parts[c])
            if parts[c] and present / total_w >= CFG["min_indicator_share_per_domain"]:
                domain_scores[c][dom["id"]] = weighted_mean(parts[c])

    dom_w = {d["id"]: d["weight"] for d in CFG["domains"]}

    def overall(c: str, weights: dict[str, float]) -> float | None:
        ds = domain_scores[c]
        if len(ds) < CFG["min_domains_for_overall"]:
            return None
        return weighted_mean([(s, weights[d]) for d, s in ds.items()])

    def ranks(weights: dict[str, float]) -> dict[str, int]:
        scored = {c: overall(c, weights) for c in countries}
        order = sorted((c for c in countries if scored[c] is not None), key=lambda c: -scored[c])
        return {c: i + 1 for i, c in enumerate(order)}

    base = ranks(dom_w)
    rng = random.Random(CFG["sensitivity"]["seed"])
    samples: dict[str, list[int]] = {c: [] for c in base}
    for _ in range(CFG["sensitivity"]["samples"]):
        raw = [rng.expovariate(1.0) for _ in dom_w]  # uniform over the weight simplex
        w = dict(zip(dom_w, raw))
        for c, r in ranks(w).items():
            samples[c].append(r)

    def pct(xs: list[int], q: float) -> int:
        s = sorted(xs)
        return s[min(len(s) - 1, int(q * len(s)))]

    rows = []
    for c in countries:
        o = overall(c, dom_w)
        row = {
            "iso3": c,
            "overall": round(o, 1) if o is not None else None,
            "rank": base.get(c),
            "rank_range": [pct(samples[c], 0.05), pct(samples[c], 0.95)] if c in samples else None,
            "domains": {d: round(s, 1) for d, s in domain_scores[c].items()},
            "missing_domains": [d["id"] for d in CFG["domains"] if d["id"] not in domain_scores[c]],
            "indicators": detail[c],
        }
        rows.append(row)
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0))
    return {"rows": rows, "ranked": len(base)}


def main() -> None:
    data = load_indicators()
    n = names()
    excluded = CFG.get("excluded_countries", {})
    countries = [c for c in n if c not in excluded and c in data]
    result = compute(data, countries)
    for r in result["rows"]:
        r["name"] = n.get(r["iso3"], r["iso3"])
    out = {
        "method_version": CFG["version"],
        "computed": dt.date.today().isoformat(),
        "countries_compared": len(countries),
        "domains": [{k: d[k] for k in ("id", "label", "weight", "question")} for d in CFG["domains"]],
        "not_yet_scored": CFG["not_yet_scored"],
        "excluded_countries": excluded,
        "rows": result["rows"],
    }
    (ROOT / "data" / "scores.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{'#':>2}  {'country':<15} {'score':>5}  {'range':>7}   " + "  ".join(f"{d['id'][:10]:>10}" for d in CFG["domains"]))
    for r in out["rows"]:
        rr = f"{r['rank_range'][0]}-{r['rank_range'][1]}" if r["rank_range"] else "-"
        doms = "  ".join(f"{r['domains'].get(d['id'], float('nan')):>10.1f}" for d in CFG["domains"])
        print(f"{r['rank'] or '-':>2}  {r['name']:<15} {r['overall'] if r['overall'] is not None else '-':>5}  {rr:>7}   {doms}")


if __name__ == "__main__":
    main()

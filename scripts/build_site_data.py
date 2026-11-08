"""Bundle data/ into site/data/ for the static site.

  python scripts/build_site_data.py

Writes site/data/index.json (one row per country) and copies each country
profile and indicator file. Used by the deploy workflow and for local previews.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "site" / "data"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "countries").mkdir(parents=True)
    (OUT / "indicators").mkdir(parents=True)

    index = []
    for f in sorted((DATA / "countries").glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        claims = [c for cs in p["sections"].values() for c in cs]
        verified = sum(1 for c in claims if c["verification"]["passage_found"] == "pass"
                       and c["verification"]["supports"] == "pass")
        index.append({
            "iso3": p["iso3"], "name": p["name"], "status": p["status"],
            "model_type": p["model"]["type"], "model": p["model"]["label"],
            "system_as_of": p["system_as_of"], "claims": len(claims), "verified": verified,
            "sources": len(p["sources"]), "is_baseline": p.get("is_baseline", False),
        })
        shutil.copy(f, OUT / "countries" / f.name)

    for f in sorted((DATA / "indicators").glob("*.json")):
        shutil.copy(f, OUT / "indicators" / f.name)

    (OUT / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    # Same data as one script file, so the site also works when index.html is
    # opened straight from disk (browsers block fetch() on file:// pages).
    bundle = {"data/index.json": index}
    for f in sorted(OUT.glob("*/*.json")):
        bundle[f"data/{f.parent.name}/{f.name}"] = json.loads(f.read_text(encoding="utf-8"))
    (OUT / "bundle.js").write_text(
        "window.ATLAS_DATA = " + json.dumps(bundle, ensure_ascii=False) + ";\n", encoding="utf-8")

    print(f"site/data: {len(index)} profiles, indicators for {len(list((OUT / 'indicators').glob('*.json')))} countries")


if __name__ == "__main__":
    main()

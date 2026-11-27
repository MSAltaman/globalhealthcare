#!/usr/bin/env python3
"""Load the atlas into BigQuery: one table per kind of record, rebuilt from the repo.

GitHub is the master copy. Every load replaces each table's contents
(WRITE_TRUNCATE), so a structure change is a change to this file followed by a
reload: no migrations. Each row keeps its full original record in a `raw` JSON
column, so fields that are not columns yet can still be queried with
JSON_VALUE(raw, '$.field').

Usage:
  python scripts/load_bigquery.py --dry-run [--out build/bigquery]
      Write every table as newline-delimited JSON plus its schema, and the views
      as SQL, without touching Google Cloud. Tests and CI use this.
  python scripts/load_bigquery.py --dataset healthcare-atlas-staging.atlas_staging
      Load all tables, apply the views in bigquery/views/, then check that each
      table's row count matches the files. Uses Application Default Credentials
      (in CI: google-github-actions/auth with Workload Identity Federation).
  python scripts/load_bigquery.py --dataset healthcare-atlas-staging.atlas_ci --table-suffix _pr40
      Same, with every table and view name suffixed, for a pull request's own
      copy. Tables in atlas_ci expire after a day.

Loading needs google-cloud-bigquery (pip install google-cloud-bigquery);
--dry-run needs only the standard library.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "bigquery" / "views"


# ---------------------------------------------------------------------------
# Schemas. Field types are BigQuery's; "mode" defaults to NULLABLE.
# ---------------------------------------------------------------------------

def f(name: str, type_: str, mode: str = "NULLABLE", description: str = "") -> dict:
    field = {"name": name, "type": type_, "mode": mode}
    if description:
        field["description"] = description
    return field


RAW = f("raw", "JSON", description="The full original record from the repository")

SCHEMAS: dict[str, list[dict]] = {
    "countries": [
        f("iso3", "STRING", "REQUIRED"), f("name", "STRING"), f("wave", "INT64"),
        f("is_baseline", "BOOL"), f("has_profile", "BOOL", description="A profile exists in data/countries"),
        f("status", "STRING"), f("system_as_of", "DATE"),
        f("model_type", "STRING"), f("model_label", "STRING"),
        f("meets_universal_definition", "BOOL"),
        f("claim_count", "INT64"), f("verified_claim_count", "INT64"),
        f("source_count", "INT64"), f("ranking_count", "INT64"),
        f("why_included", "STRING", description="Why the country is in scope (config/countries.json)"),
        RAW,
    ],
    "claims": [
        f("claim_id", "STRING", "REQUIRED"), f("iso3", "STRING", "REQUIRED"), f("section", "STRING"),
        f("position", "INT64", description="Order within its section, from 1"),
        f("statement", "STRING"), f("valence", "STRING"),
        f("data_year", "STRING", description="As recorded: usually a year, sometimes a range"),
        f("historical", "BOOL"), f("source_id", "STRING"),
        f("locator_page", "STRING"), f("locator_section", "STRING"),
        f("locator_table", "STRING"), f("locator_figure", "STRING"),
        f("passage_found", "STRING"), f("supports", "STRING"),
        f("checked_on", "DATE"), f("checked_by", "STRING"), f("verification_note", "STRING"),
        RAW,
    ],
    "sources": [
        f("source_id", "STRING", "REQUIRED"), f("iso3", "STRING", "REQUIRED"),
        f("title", "STRING"), f("publisher", "STRING"), f("authors", "STRING"),
        f("year", "INT64"), f("tier", "INT64"), f("type", "STRING"),
        f("url", "STRING"), f("text_url", "STRING"), f("doi", "STRING"), f("license", "STRING"),
        f("funding_note", "STRING"), f("accessed", "DATE"),
        f("claim_count", "INT64", description="Claims in this country's profile citing the source"),
        RAW,
    ],
    "rankings": [
        f("iso3", "STRING", "REQUIRED"), f("study", "STRING"), f("year", "INT64"),
        f("domain", "STRING"), f("position", "INT64"), f("of_total", "INT64"),
        f("source_id", "STRING"), RAW,
    ],
    "indicators": [
        f("iso3", "STRING", "REQUIRED"), f("indicator_id", "STRING", "REQUIRED"),
        f("label", "STRING"), f("unit", "STRING"), f("indicator_group", "STRING"),
        f("value", "FLOAT64"), f("year", "INT64"),
        f("original_source", "STRING"), f("api_url", "STRING"), f("retrieved", "DATE"),
        RAW,
    ],
    "financing_revenue": [
        f("iso3", "STRING", "REQUIRED"), f("year", "INT64"), f("segment_id", "STRING"),
        f("label", "STRING"), f("pct_gdp", "FLOAT64"), f("total_pct_gdp", "FLOAT64"),
        f("share_of_total", "FLOAT64", description="pct_gdp / total_pct_gdp, from 0 to 1"),
        f("source", "STRING"), RAW,
    ],
    "scores": [
        f("iso3", "STRING", "REQUIRED"), f("name", "STRING"),
        f("overall", "FLOAT64"), f("rank", "INT64"), f("rank_low", "INT64"), f("rank_high", "INT64"),
        f("missing_domains", "STRING", "REPEATED"),
        f("method_version", "STRING"), f("computed", "DATE"), RAW,
    ],
    "score_domains": [
        f("iso3", "STRING", "REQUIRED"), f("domain", "STRING", "REQUIRED"), f("label", "STRING"),
        f("score", "FLOAT64"),
        f("position", "INT64", description="Position among countries scored in this domain, 1 = best"),
        f("domain_weight", "FLOAT64"),
    ],
    "score_indicators": [
        f("iso3", "STRING", "REQUIRED"), f("domain", "STRING", "REQUIRED"),
        f("indicator_id", "STRING", "REQUIRED"), f("label", "STRING"), f("unit", "STRING"),
        f("value", "FLOAT64"), f("year", "INT64"), f("score", "FLOAT64"),
        f("weight", "FLOAT64"), f("better", "STRING"), f("scale", "STRING"), f("log_scale", "BOOL"),
        f("zero_at", "FLOAT64", description="The value that scores 0, for world-scaled measures"),
        f("hundred_at", "FLOAT64", description="The value that scores 100, for world-scaled measures"),
        RAW,
    ],
    "load_metadata": [
        f("table_name", "STRING", "REQUIRED"), f("row_count", "INT64"),
        f("git_commit", "STRING"), f("loaded_at", "TIMESTAMP"), f("method_version", "STRING"),
    ],
}


# ---------------------------------------------------------------------------
# Flattening: repository files -> rows
# ---------------------------------------------------------------------------

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def as_date(value) -> str | None:
    """Keep a value only if it is an ISO date (BigQuery DATE rejects anything else)."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return None


def as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return None


def as_float(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_str(value) -> str | None:
    return None if value is None else str(value)


def build_tables(root: Path = ROOT, git_commit: str | None = None, now: dt.datetime | None = None) -> dict[str, list[dict]]:
    """Read the repository and return {table name: rows}."""
    config = read_json(root / "config" / "countries.json")
    in_scope = {}
    for wave in config.get("waves", []):
        for c in wave.get("countries", []):
            in_scope[c["iso3"]] = {**c, "wave": wave.get("wave")}
    baseline = (config.get("baseline") or {}).get("iso3") if isinstance(config.get("baseline"), dict) else config.get("baseline")

    profiles = {p.stem: read_json(p) for p in sorted((root / "data" / "countries").glob("*.json"))}
    indicator_files = {p.stem: read_json(p) for p in sorted((root / "data" / "indicators").glob("*.json"))}
    scores_path = root / "data" / "scores.json"
    scores = read_json(scores_path) if scores_path.exists() else {"rows": [], "domains": []}

    tables: dict[str, list[dict]] = {name: [] for name in SCHEMAS}

    # countries: everything in scope, plus any profile not (yet) in the config
    for iso3 in sorted(set(in_scope) | set(profiles)):
        cfg, p = in_scope.get(iso3, {}), profiles.get(iso3)
        claims = [c for lst in (p or {}).get("sections", {}).values() if isinstance(lst, list) for c in lst]
        tables["countries"].append({
            "iso3": iso3,
            "name": (p or {}).get("name") or cfg.get("name"),
            "wave": as_int((p or {}).get("wave", cfg.get("wave"))),
            "is_baseline": bool((p or {}).get("is_baseline")) or iso3 == baseline,
            "has_profile": p is not None,
            "status": (p or {}).get("status"),
            "system_as_of": as_date((p or {}).get("system_as_of")),
            "model_type": ((p or {}).get("model") or {}).get("type"),
            "model_label": ((p or {}).get("model") or {}).get("label"),
            "meets_universal_definition": ((p or {}).get("universal_coverage") or {}).get("meets_definition"),
            "claim_count": len(claims),
            "verified_claim_count": sum(1 for c in claims if (c.get("verification") or {}).get("passage_found") == "pass"
                                        and (c.get("verification") or {}).get("supports") == "pass"),
            "source_count": len((p or {}).get("sources", [])),
            "ranking_count": len((p or {}).get("rankings", [])),
            "why_included": cfg.get("why"),
            "raw": p if p is not None else cfg,
        })

    for iso3, p in profiles.items():
        cites: dict[str, int] = {}
        for section, lst in p.get("sections", {}).items():
            if not isinstance(lst, list):
                continue
            for i, c in enumerate(lst, 1):
                loc, ver = c.get("locator") or {}, c.get("verification") or {}
                cites[c.get("source_id")] = cites.get(c.get("source_id"), 0) + 1
                tables["claims"].append({
                    "claim_id": c.get("id"), "iso3": iso3, "section": section, "position": i,
                    "statement": c.get("statement"), "valence": c.get("valence"),
                    "data_year": as_str(c.get("data_year")), "historical": bool(c.get("historical", False)),
                    "source_id": c.get("source_id"),
                    "locator_page": as_str(loc.get("page")), "locator_section": as_str(loc.get("section")),
                    "locator_table": as_str(loc.get("table")), "locator_figure": as_str(loc.get("figure")),
                    "passage_found": ver.get("passage_found"), "supports": ver.get("supports"),
                    "checked_on": as_date(ver.get("checked_on")), "checked_by": ver.get("checked_by"),
                    "verification_note": ver.get("note"),
                    "raw": c,
                })
        for s in p.get("sources", []):
            tables["sources"].append({
                "source_id": s.get("id"), "iso3": iso3, "title": s.get("title"), "publisher": s.get("publisher"),
                "authors": as_str(s.get("authors")), "year": as_int(s.get("year")), "tier": as_int(s.get("tier")),
                "type": s.get("type"), "url": s.get("url"), "text_url": s.get("text_url"), "doi": s.get("doi"),
                "license": s.get("license"), "funding_note": s.get("funding_note"), "accessed": as_date(s.get("accessed")),
                "claim_count": cites.get(s.get("id"), 0),
                "raw": s,
            })
        for r in p.get("rankings", []):
            tables["rankings"].append({
                "iso3": iso3, "study": r.get("study"), "year": as_int(r.get("year")), "domain": r.get("domain"),
                "position": as_int(r.get("position")), "of_total": as_int(r.get("of")),
                "source_id": r.get("source_id"), "raw": r,
            })

    for iso3, d in indicator_files.items():
        for i in d.get("indicators", []):
            tables["indicators"].append({
                "iso3": iso3, "indicator_id": i.get("id"), "label": i.get("label"), "unit": i.get("unit"),
                "indicator_group": i.get("group"), "value": as_float(i.get("value")), "year": as_int(i.get("year")),
                "original_source": i.get("original_source"), "api_url": i.get("api_url"),
                "retrieved": as_date(d.get("retrieved")), "raw": i,
            })
        fr = d.get("financing_revenue") or {}
        total = as_float(fr.get("total_pct_gdp"))
        for s in fr.get("segments", []) or []:
            pct = as_float(s.get("pct_gdp"))
            tables["financing_revenue"].append({
                "iso3": iso3, "year": as_int(fr.get("year")), "segment_id": s.get("id"), "label": s.get("label"),
                "pct_gdp": pct, "total_pct_gdp": total,
                "share_of_total": (pct / total) if pct is not None and total else None,
                "source": fr.get("source"), "raw": s,
            })

    domains = {d["id"]: d for d in scores.get("domains", [])}
    bench = {(dom_id, i["id"]): i for dom_id, d in domains.items() for i in d.get("indicators", []) or []}
    for r in scores.get("rows", []):
        rr = r.get("rank_range") or [None, None]
        tables["scores"].append({
            "iso3": r["iso3"], "name": r.get("name"), "overall": as_float(r.get("overall")),
            "rank": as_int(r.get("rank")), "rank_low": as_int(rr[0]), "rank_high": as_int(rr[1]),
            "missing_domains": list(r.get("missing_domains") or []),
            "method_version": scores.get("method_version"), "computed": as_date(scores.get("computed")),
            "raw": r,
        })
        for dom_id, inds in (r.get("indicators") or {}).items():
            for ind_id, v in inds.items():
                b = bench.get((dom_id, ind_id), {})
                tables["score_indicators"].append({
                    "iso3": r["iso3"], "domain": dom_id, "indicator_id": ind_id,
                    "label": b.get("label"), "unit": b.get("unit"),
                    "value": as_float(v.get("value")), "year": as_int(v.get("year")), "score": as_float(v.get("score")),
                    "weight": as_float(b.get("weight")), "better": b.get("better"), "scale": b.get("scale"),
                    "log_scale": b.get("log"), "zero_at": as_float(b.get("zero_at")), "hundred_at": as_float(b.get("hundred_at")),
                    "raw": v,
                })
    for dom_id in sorted({d for r in scores.get("rows", []) for d in (r.get("domains") or {})}):
        scored = sorted((r for r in scores["rows"] if (r.get("domains") or {}).get(dom_id) is not None),
                        key=lambda r: -r["domains"][dom_id])
        for pos, r in enumerate(scored, 1):
            tables["score_domains"].append({
                "iso3": r["iso3"], "domain": dom_id, "label": domains.get(dom_id, {}).get("label"),
                "score": as_float(r["domains"][dom_id]), "position": pos,
                "domain_weight": as_float(domains.get(dom_id, {}).get("weight")),
            })

    loaded_at = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name in SCHEMAS:
        if name == "load_metadata":
            continue
        tables["load_metadata"].append({
            "table_name": name, "row_count": len(tables[name]), "git_commit": git_commit,
            "loaded_at": loaded_at, "method_version": scores.get("method_version"),
        })
    return tables


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

TABLE_REF = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_view(sql: str, dataset: str, suffix: str = "") -> str:
    """Replace {{table}} with the fully qualified, suffixed table name."""
    def sub(m):
        name = m.group(1)
        if name not in SCHEMAS and name not in views():
            raise ValueError(f"view refers to unknown table or view {{{{{name}}}}}")
        return f"`{dataset}.{name}{suffix}`"
    return TABLE_REF.sub(sub, sql)


def views() -> dict[str, str]:
    """View name -> SQL, in file-name order (prefix a view with 10_, 20_ to order dependencies)."""
    return {p.stem.split("_", 1)[1] if re.match(r"\d+_", p.stem) else p.stem: p.read_text(encoding="utf-8")
            for p in sorted(VIEWS_DIR.glob("*.sql"))}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def check_row(table: str, row: dict) -> None:
    names = {fld["name"] for fld in SCHEMAS[table]}
    extra = set(row) - names
    if extra:
        raise ValueError(f"{table}: fields not in schema: {sorted(extra)}")
    for fld in SCHEMAS[table]:
        if fld["mode"] == "REQUIRED" and row.get(fld["name"]) in (None, ""):
            raise ValueError(f"{table}: required field {fld['name']} missing in {json.dumps(row)[:200]}")


def write_dry_run(tables: dict[str, list[dict]], out: Path, dataset: str = "PROJECT.DATASET", suffix: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        for row in rows:
            check_row(name, row)
        (out / f"{name}.ndjson").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        (out / f"{name}.schema.json").write_text(json.dumps(SCHEMAS[name], indent=2) + "\n", encoding="utf-8")
    vdir = out / "views"
    vdir.mkdir(exist_ok=True)
    for name, sql in views().items():
        (vdir / f"{name}.sql").write_text(render_view(sql, dataset, suffix), encoding="utf-8")


def load(tables: dict[str, list[dict]], dataset: str, suffix: str = "") -> None:
    try:
        from google.cloud import bigquery
    except ImportError:
        sys.exit("Loading needs google-cloud-bigquery: pip install google-cloud-bigquery")
    project = dataset.split(".")[0]
    client = bigquery.Client(project=project)
    import io

    for name, rows in tables.items():
        for row in rows:
            check_row(name, row)
        table_id = f"{dataset}.{name}{suffix}"
        cfg = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=[bigquery.SchemaField.from_api_repr(fld) for fld in SCHEMAS[name]],
        )
        data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
        client.load_table_from_file(io.BytesIO(data), table_id, job_config=cfg).result()
        print(f"loaded {table_id}: {len(rows)} rows")

    for name, sql in views().items():
        view_id = f"{dataset}.{name}{suffix}"
        client.query(f"CREATE OR REPLACE VIEW `{view_id}` AS\n{render_view(sql, dataset, suffix)}").result()
        print(f"view {view_id}")

    # Post-load check: every table holds exactly the rows the files produced, and every view runs.
    problems = []
    for name, rows in tables.items():
        got = list(client.query(f"SELECT COUNT(*) AS n FROM `{dataset}.{name}{suffix}`").result())[0].n
        if got != len(rows):
            problems.append(f"{name}: {got} rows in BigQuery, {len(rows)} from the files")
    for name in views():
        client.query(f"SELECT * FROM `{dataset}.{name}{suffix}` LIMIT 1").result()
    if problems:
        sys.exit("Row counts don't match:\n  " + "\n  ".join(problems))
    print("post-load check: row counts match and every view runs")


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="write NDJSON, schemas and views to --out only")
    mode.add_argument("--dataset", help="PROJECT.DATASET to load, e.g. healthcare-atlas-staging.atlas_staging")
    ap.add_argument("--out", default=str(ROOT / "build" / "bigquery"), help="dry-run output folder")
    ap.add_argument("--table-suffix", default="", help="appended to every table and view name, e.g. _pr40")
    args = ap.parse_args(argv)
    if args.table_suffix and not re.fullmatch(r"_[A-Za-z0-9_]{1,40}", args.table_suffix):
        ap.error("--table-suffix must start with _ and use letters, digits and _ only")

    tables = build_tables(git_commit=git_commit())
    counts = ", ".join(f"{k} {len(v)}" for k, v in tables.items())
    if args.dry_run:
        write_dry_run(tables, Path(args.out), suffix=args.table_suffix)
        print(f"dry run: wrote {Path(args.out)} ({counts})")
    else:
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]\.[A-Za-z_][A-Za-z0-9_]*", args.dataset):
            ap.error("--dataset must look like PROJECT.DATASET")
        load(tables, args.dataset, args.table_suffix)


if __name__ == "__main__":
    main()

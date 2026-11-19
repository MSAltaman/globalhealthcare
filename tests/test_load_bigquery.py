"""Tests for scripts/load_bigquery.py: the flattening, the schemas and the views.

The view test runs every view against the flattened data in DuckDB, after
translating BigQuery SQL with sqlglot. It is skipped if those two packages
aren't installed; the real check is the post-load step against BigQuery.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import load_bigquery as lb  # noqa: E402

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def tables():
    return lb.build_tables(ROOT, git_commit="test", now=NOW)


def profiles():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data" / "countries").glob("*.json")}


def indicator_files():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data" / "indicators").glob("*.json")}


def test_every_claim_lands_once(tables):
    expected = {(iso3, c["id"]) for iso3, p in profiles().items()
                for lst in p["sections"].values() if isinstance(lst, list) for c in lst}
    got = [(r["iso3"], r["claim_id"]) for r in tables["claims"]]
    assert len(got) == len(set(got)), "a claim appears twice"
    assert set(got) == expected


def test_every_source_and_ranking_lands_once(tables):
    ps = profiles()
    assert sorted((r["iso3"], r["source_id"]) for r in tables["sources"]) == \
        sorted((iso3, s["id"]) for iso3, p in ps.items() for s in p.get("sources", []))
    assert len(tables["rankings"]) == sum(len(p.get("rankings", [])) for p in ps.values())


def test_claim_counts_add_up(tables):
    by_country = {r["iso3"]: r for r in tables["countries"]}
    for iso3, p in profiles().items():
        n = sum(len(lst) for lst in p["sections"].values() if isinstance(lst, list))
        assert by_country[iso3]["claim_count"] == n
        assert sum(r["claim_count"] for r in tables["sources"] if r["iso3"] == iso3) == n


def test_indicators_and_financing_match_files(tables):
    files = indicator_files()
    assert len(tables["indicators"]) == sum(len(d["indicators"]) for d in files.values())
    assert len(tables["financing_revenue"]) == sum(len((d.get("financing_revenue") or {}).get("segments") or [])
                                                  for d in files.values())
    for iso3 in {r["iso3"] for r in tables["financing_revenue"]}:
        shares = [r["share_of_total"] for r in tables["financing_revenue"] if r["iso3"] == iso3]
        assert abs(sum(shares) - 1) < 0.02, f"{iso3}: financing shares sum to {sum(shares)}"


def test_scores_match_file(tables):
    scores = json.loads((ROOT / "data" / "scores.json").read_text(encoding="utf-8"))
    assert len(tables["scores"]) == len(scores["rows"])
    assert len(tables["score_domains"]) == sum(len(r["domains"]) for r in scores["rows"])
    assert len(tables["score_indicators"]) == sum(len(v) for r in scores["rows"] for v in (r.get("indicators") or {}).values())
    for dom in {r["domain"] for r in tables["score_domains"]}:
        pos = sorted(r["position"] for r in tables["score_domains"] if r["domain"] == dom)
        assert pos == list(range(1, len(pos) + 1))


def test_load_metadata_counts(tables):
    meta = {r["table_name"]: r["row_count"] for r in tables["load_metadata"]}
    assert set(meta) == set(lb.SCHEMAS) - {"load_metadata"}
    for name, n in meta.items():
        assert n == len(tables[name])


TYPE_CHECK = {
    "STRING": lambda v: isinstance(v, str),
    "INT64": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "FLOAT64": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "BOOL": lambda v: isinstance(v, bool),
    "DATE": lambda v: isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v),
    "TIMESTAMP": lambda v: isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", v),
    "JSON": lambda v: True,
}


def test_rows_fit_their_schemas(tables):
    for name, rows in tables.items():
        for row in rows:
            lb.check_row(name, row)
            for fld in lb.SCHEMAS[name]:
                v = row.get(fld["name"])
                if v is None:
                    continue
                if fld["mode"] == "REPEATED":
                    assert isinstance(v, list) and all(TYPE_CHECK[fld["type"]](x) for x in v), (name, fld["name"], v)
                else:
                    assert TYPE_CHECK[fld["type"]](v), (name, fld["name"], v)


def test_views_refer_to_known_tables():
    names = lb.views()
    assert names, "no views in bigquery/views"
    for name, sql in names.items():
        rendered = lb.render_view(sql, "proj.ds", "_pr1")
        assert "{{" not in rendered
        for ref in re.findall(r"`proj\.ds\.(\w+)`", rendered):
            assert ref.endswith("_pr1") and (ref[:-4] in lb.SCHEMAS or ref[:-4] in names), ref


def test_unknown_table_is_rejected():
    with pytest.raises(ValueError):
        lb.render_view("SELECT * FROM {{no_such_table}}", "proj.ds")


DUCK_TYPES = {"STRING": "VARCHAR", "INT64": "BIGINT", "FLOAT64": "DOUBLE", "BOOL": "BOOLEAN",
              "DATE": "DATE", "TIMESTAMP": "TIMESTAMP", "JSON": "JSON"}


def test_views_run(tables, tmp_path):
    sqlglot = pytest.importorskip("sqlglot")
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    lb.write_dry_run(tables, tmp_path)
    for name in lb.SCHEMAS:
        cols = ", ".join(f'"{fld["name"]}" {DUCK_TYPES[fld["type"]]}{"[]" if fld["mode"] == "REPEATED" else ""}'
                         for fld in lb.SCHEMAS[name])
        con.execute(f'CREATE TABLE "{name}" ({cols})')
        rows = tables[name]
        if rows:
            path = tmp_path / f"{name}.ndjson"
            colspec = {fld["name"]: DUCK_TYPES[fld["type"]] + ("[]" if fld["mode"] == "REPEATED" else "") for fld in lb.SCHEMAS[name]}
            con.execute(f"INSERT INTO \"{name}\" SELECT * FROM read_json(?, format='newline_delimited', columns={colspec!r})",
                        [str(path)])
        assert con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] == len(rows)
    for name, sql in lb.views().items():
        bare = lb.TABLE_REF.sub(lambda m: m.group(1), sql)
        duck = sqlglot.transpile(bare, read="bigquery", write="duckdb")[0]
        con.execute(f'CREATE VIEW "{name}" AS {duck}')
        con.execute(f'SELECT * FROM "{name}"').fetchall()
    n_countries = con.execute('SELECT COUNT(*) FROM "country_comparison"').fetchone()[0]
    assert n_countries == len(tables["countries"])

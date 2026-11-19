# The atlas in BigQuery

`scripts/load_bigquery.py` rebuilds these tables from the repository on every
release. GitHub is the master copy: never edit the tables by hand, because the
next load replaces them. To change the structure, change the loader and reload.

| Dataset | Project | Rebuilt |
|---|---|---|
| `atlas_ci` | `healthcare-atlas-staging` | on each pull request, tables suffixed `_pr<number>`, deleted after a day |
| `atlas_staging` | `healthcare-atlas-staging` | on each merge to `main` |
| `atlas` | `healthcare-atlas-prod` | on each approved release |

## Tables

| Table | One row per |
|---|---|
| `countries` | country in scope (`config/countries.json`), with or without a profile yet |
| `claims` | claim, with its section, valence, data year, locator and both verification results |
| `sources` | source cited in a country profile, with how many of that profile's claims cite it |
| `rankings` | published ranking position recorded in a profile |
| `indicators` | statistic per country (World Bank, WHO, OECD), with year and API URL |
| `financing_revenue` | financing segment per country, as % of GDP and share of the total |
| `scores` | country's overall atlas score, rank and rank range |
| `score_domains` | country × scored area (coverage, financial protection, outcomes), with position |
| `score_indicators` | country × scored measure: value, year, 0–100 score, weight, and the values that score 0 and 100 |
| `load_metadata` | table per load: row count, git commit, load time |

Every table except `score_domains` and `load_metadata` has a `raw` JSON column
holding the full original record, so a field that isn't a column yet can still
be queried: `JSON_VALUE(raw, '$.locator.char_start')`.

## Views (`bigquery/views/`)

| View | Answers |
|---|---|
| `financing_mix` | Who pays: taxes, social insurance, premiums, out of pocket, as shares of spending |
| `country_comparison` | One row per country: scores, key statistics, financing mix, claim and source counts |
| `us_vs_countries` | Every statistic next to the US value, with the difference and ratio |
| `claims_with_sources` | Every claim with the source it cites |
| `sources_by_publisher` | How much of the atlas rests on each publisher |
| `strengths_vs_problems` | Balance of what works and what doesn't, per country |

Views are plain `.sql` files; `{{table}}` is replaced with the full table name
when they're applied. Prefix a new file with a number to set its order, for
example `70_my_view.sql`; a view can refer to an earlier one by name.

## Example queries

```sql
-- Countries that spend less per person than the US but live longer.
SELECT name, health_spending_per_person_ppp, life_expectancy
FROM `healthcare-atlas-staging.atlas_staging.country_comparison`
WHERE health_spending_per_person_ppp < (SELECT health_spending_per_person_ppp
                                        FROM `healthcare-atlas-staging.atlas_staging.country_comparison`
                                        WHERE iso3 = 'USA')
  AND life_expectancy > (SELECT life_expectancy
                         FROM `healthcare-atlas-staging.atlas_staging.country_comparison`
                         WHERE iso3 = 'USA')
ORDER BY life_expectancy DESC;

-- Every claim about waiting times, with its source.
SELECT country, statement, source_title, publisher, source_year
FROM `healthcare-atlas-staging.atlas_staging.claims_with_sources`
WHERE REGEXP_CONTAINS(LOWER(statement), r'wait')
ORDER BY country;

-- Which measure costs each country the most outcome points.
SELECT iso3, label, value, year, score, weight
FROM `healthcare-atlas-staging.atlas_staging.score_indicators`
WHERE domain = 'outcomes'
QUALIFY ROW_NUMBER() OVER (PARTITION BY iso3 ORDER BY (100 - score) * weight DESC) = 1
ORDER BY score;
```

## Running it yourself

```sh
python scripts/load_bigquery.py --dry-run            # writes build/bigquery/, touches nothing
pip install google-cloud-bigquery
gcloud auth application-default login
python scripts/load_bigquery.py --dataset healthcare-atlas-staging.atlas_staging
```
Loading by hand needs write access to the dataset; normally the pipeline does it
as the `deployer@` account.

# Global Healthcare Atlas

A country-by-country comparison of universal health systems: what each one
provides, what it subsidizes, the options for additional care, outcomes,
costs, what works, what doesn't, and what the evidence says for the United
States.

Every statement on the site is tied to a source and an exact location in it,
and passes two checks before it is published:

1. **Code check** — a fingerprint of the supporting passage is confirmed to
   still exist, unchanged, in the current version of the source; the statement
   is confirmed not to copy the source's wording.
2. **Model check** — a separate pass confirms the passage supports the
   statement exactly as written.

Statistics come straight from the World Bank API (which republishes WHO and UN
series); no number is written by hand or by a model.

## Status

Pilot: Germany, Japan, Mexico. See `config/countries.json` for the waves.

## Run the checks locally

```bash
pip install requests beautifulsoup4 pypdf jsonschema pytest
python -m pytest tests
python scripts/validate.py
python scripts/verify_claims.py --check
```

## How it's built

- **Research agent:** a scheduled Claude task that follows `CLAUDE.md`, works on
  a `claude/` branch and opens a pull request.
- **Review:** each pull request gets a preview site; a human merges.
- **Site:** static files in `site/`, hosted on Azure Static Web Apps.
- **Infrastructure:** `infra/` holds Bicep for the site and for a fully
  Azure-hosted version of the agent (later phase).

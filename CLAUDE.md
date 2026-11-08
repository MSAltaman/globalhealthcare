# Global Healthcare Atlas — agent instructions

This repository is a research agent's workspace. Its job: a country-by-country,
fully sourced comparison of universal health systems, with the United States as
the comparison baseline, published as a static site.

The site argues nothing. It reports what each system provides, what it costs,
how well it performs, what works and what doesn't, and what the evidence says
about lessons for the US. Strengths and failures get equal care.

## Non-negotiable rules

1. **Every statement is a claim with a source.** No sentence reaches
   `data/countries/*.json` without a `source_id` and a `locator` (page,
   section, table or figure).
2. **No numbers from memory.** Comparable statistics come only from
   `scripts/fetch_indicators.py`. Any other number in a claim must appear in
   the cited source at the cited locator.
3. **Never copy source text into the repo.** Write each statement in your own
   words. Anchor it with `scripts/sourcetext.py locate` (the passage goes in on
   stdin and is never written to a file). The verifier fails any statement
   that shares 12+ consecutive words with its source.
4. **Prefer the best available source.** Follow the tiers in
   `config/sources.json`. Tier 4 (news, explainers) can never be a claim's
   only support. Record the funder or stance of tier-3 sources in
   `funding_note` when it bears on bias.
5. **Current, and dated.** Check for reforms in the last five years before
   describing a system. Every claim records `data_year` when the data year
   differs from publication. A study describing a system that has since been
   reformed must say so in the statement.
6. **Balance.** Every profile needs at least three `what_works` and three
   `problems` claims, from more than one source each.
7. **Rankings are findings.** Write "ranked 2nd of 10 in X's 2024 study", never
   "has the 2nd best system". Put them in `rankings`, with the source.
8. **US lessons only from evidence.** `us_lessons` claims must come from tier
   1-3 sources that address the US or cross-country transferability directly.
   No extrapolation of our own.
9. **When unsure, leave it out.** A missing claim is better than a wrong one.

## The two checks every claim must pass

| Field | Who sets it | Meaning |
|---|---|---|
| `verification.passage_found` | `scripts/verify_claims.py` (code) | The fingerprinted passage is still in the source, unchanged, and the statement doesn't copy it |
| `verification.supports` | The model, in a separate pass | Re-read the passage and the statement cold: does the passage support the statement exactly as written, including numbers, years and scope? |

For the `supports` pass, read only the passage and the statement, not your
earlier reasoning. Mark `fail` for any overstatement, wrong year, wrong scope
or number mismatch, and fix or drop the claim.

A profile is `verified` only when every claim passes both checks.

## How a run works

The scheduled task runs this procedure. Each run handles at most the number of
countries in its prompt (default 3).

1. **Pick countries.** In order: profiles with `status: needs_review`; then
   countries in `config/countries.json` with no profile, by wave; then
   profiles whose `system_as_of` is older than 6 months.
2. **Pull indicators.** `python scripts/fetch_indicators.py <ISO3...>`
3. **Research each country.**
   - Start with the tier-1 system review (European Observatory Health Systems
     in Transition, or the WHO/Asia Pacific Observatory equivalent), the
     Commonwealth Fund country profile, and the ministry of health.
   - Search the scholarly APIs (OpenAlex, PubMed, Europe PMC) for recent
     studies on access, costs, outcomes, reforms and lessons for the US.
   - For each source: `python scripts/sourcetext.py fetch <source_id> <url>`
   - For each claim: write the statement, then
     `echo "<supporting passage>" | python scripts/sourcetext.py locate <source_id>`
     and copy the returned offsets and hash into the claim's `locator`.
4. **Supports pass.** Set `verification.supports` for every claim (see above).
5. **Verify and validate.**
   `python scripts/verify_claims.py <ISO3...>` then `python scripts/validate.py`.
   Fix anything that fails. Do not open a PR with failing claims.
6. **Open a pull request** from a `claude/` branch titled
   `research: <countries> (<date>)`, with a summary: countries touched, claims
   added/changed/removed, anything that failed and was dropped, and open
   questions for the human reviewer. The site preview builds automatically;
   a human merges.

## Files

| Path | What it is |
|---|---|
| `schema/country.schema.json` | The country data model |
| `config/countries.json` | Scope definition and the country waves |
| `config/indicators.json` | Indicators pulled from the World Bank API |
| `config/sources.json` | Source tiers and the search APIs |
| `data/countries/<ISO3>.json` | One profile per country |
| `data/indicators/<ISO3>.json` | Machine-pulled statistics |
| `scripts/` | fetch, locate, verify and validate tools (see each file's docstring) |
| `site/` | The static site; reads `data/` at build time |
| `infra/` | Azure Bicep (see `infra/README.md`) |

## Network

The run needs these domains allowed in the cloud environment, in addition to
the default package registries: `api.worldbank.org`, `ghoapi.azureedge.net`,
`sdmx.oecd.org`, `api.openalex.org`, `eutils.ncbi.nlm.nih.gov`,
`www.ebi.ac.uk`, `api.crossref.org`, plus the source sites themselves
(`eurohealthobservatory.who.int`, `iris.who.int`, `www.who.int`,
`www.oecd.org`, `www.commonwealthfund.org`, and national ministry domains),
or **Full** network access.

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

1. **Pick countries.** If the run's prompt names countries, do exactly those.
   Otherwise, in order: profiles with `status: needs_review`; then countries in
   `config/countries.json` with no profile, by wave; then profiles whose
   `system_as_of` is older than 6 months.
2. **Indicators.** `python scripts/fetch_indicators.py <ISO3...>` (skip if
   `data/indicators/<ISO3>.json` is less than a month old). Taiwan is not in
   World Bank or WHO data: cite its key statistics as ordinary claims from
   official Taiwanese sources instead.
3. **Create the profile.** `python scripts/new_profile.py <ISO3> "<Name>" --wave <n>`.
   Use `data/countries/DEU.json` as the reference for depth and style:
   about 45-60 claims, 6-9 sources, every section filled where evidence exists.
4. **Find sources.** Start with the tier-1 system review (European Observatory
   Country Health Profile 2025 or Health System Summary for EU countries;
   WHO / Asia Pacific Observatory reviews for others; OECD Health at a
   Glance), the Commonwealth Fund country profile and Mirror, Mirror 2024
   exhibits where the country is covered, and the ministry of health. Search
   Europe PMC (`https://www.ebi.ac.uk/europepmc/webservices/rest/search`,
   use `TITLE:` filters) and PubMed E-utilities for recent studies on access,
   costs, inequalities, reforms and lessons for the US. OpenAlex may rate-limit.
5. **Download each source.** `python scripts/sourcetext.py fetch <source_id> <url>`.
   - For a paywalled or bot-blocked article, keep `url` as the DOI or article
     page and set `text_url` to the open text: PMC full text
     `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=<PMCID digits>`
     or the PubMed abstract
     `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<PMID>&rettype=abstract&retmode=text`.
   - If a source cannot be downloaded (blocked domain, robots, 403), do not
     use it. Find another source for those facts, and list the blocked domain
     in the pull request so the human can allow it.
6. **Write and anchor each claim.** Write the statement in your own words
   from the passage, then anchor it:
   `python scripts/anchor.py <ISO3> <claim_id> --start "<first words>" --end "<last words>"`.
   Check the printed passage. Keep passages tight (one to three sentences).
   Claim ids are `<ISO3>-<section>-<nnn>`, numbered from 001 per section.
7. **Support review: a separate, cold pass.** After all claims are anchored,
   go back through every claim reading only the printed passage
   (`anchor.py ... --show`) and the statement. Mark `verification.supports`
   `pass` only if the passage supports the statement exactly. In the Germany
   pilot these were the common failures, so check each one:
   - **Scope:** a figure about a subgroup (people who needed care, adults,
     medicines approved 2020-2023) stated as if about everyone.
   - **Date:** a missing or wrong year, or "as of" dropped.
   - **Overstatement:** "mostly", "every", "all" where the source says less.
   - **Order and causation:** "after" vs "starting with", "because" where the
     source gives no reason.
   - **Details from elsewhere:** a number or name that is not in this passage,
     even if it is elsewhere in the document. Split the claim or drop the detail.
   Rewrite and re-anchor, or delete the claim. Set `checked_on` and
   `checked_by` (model name plus "support review").
8. **Verify and validate.**
   `python scripts/verify_claims.py <ISO3...>`, then `python scripts/validate.py`
   and `python -m pytest -q tests`. Fix anything that fails. Never open a pull
   request with a failed claim.
9. **Pull request.** Only touch your countries' files under `data/` (plus
   `config/` if a source tier note needs it). Push a `claude/research-<iso3s>`
   branch and open a PR titled `research: <Names> (<date>)`. In the PR body:
   claims and sources per country, statements dropped or corrected in review,
   blocked domains, and open questions for the reviewer.

## Files

| Path | What it is |
|---|---|
| `schema/country.schema.json` | The country data model |
| `config/countries.json` | Scope definition and the country waves |
| `config/indicators.json` | Indicators pulled from the World Bank and WHO APIs |
| `config/sources.json` | Source tiers and the search APIs |
| `data/countries/<ISO3>.json` | One profile per country |
| `data/indicators/<ISO3>.json` | Machine-pulled statistics |
| `scripts/` | `fetch_indicators`, `new_profile`, `sourcetext` (fetch), `anchor`, `verify_claims`, `validate`, `build_site_data`; see each file's docstring |
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

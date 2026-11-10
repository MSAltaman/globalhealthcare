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
5. **Current, and dated.** Claims about how things are now must rest on data
   from the last 10 years (`scripts/validate.py` enforces this using
   `data_year`, else the source's year). Prefer the most recent data that
   exists; a 2023 figure beats a 2017 one. Older data is allowed only for a
   claim that states a past event or a past level for a trend, marked
   `"historical": true` and worded in the past tense with its year. Never keep
   an old figure because it is striking or widely quoted: find the current
   equivalent, or drop the claim.
   Check for reforms in the last five years before
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

0. **Backfill first.** If `config/backfill.json` has an item with
   `status: open`, this run fills that country's gaps instead of starting a
   new country: work on its open PR branch (or `claude/backfill-<iso3>` from
   `main` if already merged), keep every existing rule and check, update the
   PR body, and set the item's `status` to `done` in the same branch.
   Because that change is not on `main` until the PR merges, an item counts
   as done if it is `done` either on `main` or in `config/backfill.json` on
   that country's branch (`git show origin/<branch>:config/backfill.json`).
   Check both before picking an item.
1. **Pick ONE country per run.** If the run's prompt names countries, take the
   first one that has neither a profile on `main` nor a remote branch
   `claude/research-<iso3>` (`git ls-remote --heads origin`). Otherwise, in
   order: profiles with `status: needs_review`; then countries in
   `config/countries.json` with no profile and no such branch, by wave; then
   profiles whose `system_as_of` is older than 6 months. If a branch
   `claude/research-<iso3>` exists with unfinished work, continue it instead.
   One country per run keeps usage low and means a usage limit never loses
   more than one country's work.
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
6. **Save progress as you go.** Work on branch `claude/research-<iso3>`.
   Commit and push after the sources are downloaded and again after every
   section's claims are anchored (`git push -u origin claude/research-<iso3>`).
   A run can stop at any time on a usage limit; the next run resumes from the
   branch.
7. **Write and anchor each claim.** Write the statement in your own words
   from the passage, then anchor it:
   `python scripts/anchor.py <ISO3> <claim_id> --start "<first words>" --end "<last words>"`.
   Check the printed passage. Keep passages tight (one to three sentences).
   Claim ids are `<ISO3>-<section>-<nnn>`, numbered from 001 per section.
8. **Support review: a separate, cold pass.** After all claims are anchored,
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
9. **Verify and validate.**
   `python scripts/verify_claims.py <ISO3...>`, then `python scripts/validate.py`
   and `python -m pytest -q tests`. Fix anything that fails. Never open a pull
   request with a failed claim.
10. **Pull request.** Only touch your country's files under `data/` (plus
   `config/` if a source tier note needs it). Open a PR from `claude/research-<iso3>` titled `research: <Names> (<date>)`. In the PR body:
   claims and sources per country, statements dropped or corrected in review,
   blocked domains, and open questions for the reviewer.

## Rankings

Record every published cross-country ranking that states the country's
position, in `rankings`, each as the source's own finding:
- **Commonwealth Fund Mirror, Mirror 2024** (10 countries: Australia, Canada,
  France, Germany, Netherlands, New Zealand, Sweden, Switzerland, UK, US):
  overall plus each domain.
- **GBD Healthcare Access and Quality (HAQ) Index** (The Lancet; 195-204
  countries), which covers every country in this atlas except Taiwan: the
  country's rank or score where the paper or its appendix table states it,
  with the data year. A table row may be anchored when the passage contains
  the country name and its values; put the table number and the column
  (year or measure) in `locator.table`.
- Other peer-reviewed or intergovernmental comparisons that rank countries,
  if the source states the position.
Do not use commercial or opinion "best healthcare" lists. If no qualifying
ranking states the country's position, leave `rankings` empty and say so in
the PR.

## Financial hardship section

Every profile fills `financial_hardship`. The comparable rates (households
spending over 10% and 25% of their budget on health, and people pushed into
poverty by health costs) are pulled automatically from WHO into
`data/indicators/`; do not restate them as claims. Instead, look for national
evidence on medical debt, arrears and personal bankruptcy or insolvency
linked to health costs: insolvency statistics that record causes, debt
counselling data, and peer-reviewed studies. Many countries do not record
medical causes of bankruptcy at all. When your search finds none, add one
claim saying so only if a source states it; otherwise leave the section empty
and note "no national data found" in the PR. Never estimate a bankruptcy rate.

For the US baseline, published estimates of medical bankruptcy disagree
sharply because they measure different things (for example, whether illness
"contributed" vs. whether a hospitalisation "caused" a filing). Report each
estimate with its definition, never one figure alone.

## United States baseline profile

The US profile (`USA.json`, `is_baseline: true`, `universal_coverage.meets_definition: false`)
uses the same sections and rules, plus these, each reported with its
definition and data year:
- **Uninsured:** count and rate from the Census Bureau (CPS ASEC and ACS
  reports), and how it changed recently.
- **Underinsured:** the Commonwealth Fund biennial coverage survey (state its
  definition of underinsured) and coverage gaps during the year.
- **Insurer decisions on care:** claim denial rates (e.g. KFF analysis of
  HealthCare.gov plans: in-network denials, appeal rates), prior authorization
  (e.g. AMA physician survey, HHS Office of Inspector General reports on
  Medicare Advantage), and how often denials are appealed and overturned.
  State the data's limits as the source does.
- **Medical debt and bankruptcy:** see the financial hardship section; report
  each bankruptcy estimate with its definition.
- **Balance still applies:** at least three `what_works` claims with evidence
  (for example cancer survival, waiting times for specialists or elective
  surgery, innovation), from tier 1-3 sources.
For other countries, record comparable evidence on who decides what care is
covered (benefit-basket bodies, budgets, waiting lists, private insurer
approval for supplementary cover) so the comparison is like for like.

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

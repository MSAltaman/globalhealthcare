# Global Healthcare Atlas — Azure infrastructure

**Phase 1 (now):** the research agent runs as a Claude scheduled task, so Azure
only hosts the site. Deploy `site-only/main.bicep` (a free Static Web App and an
optional budget alert):

```bash
az group create -n rg-hcatlas-prod -l eastus2
az deployment group create -g rg-hcatlas-prod -f site-only/main.bicep
```

**Phase 2 (later):** the fully Azure-hosted agent described below.

Bicep for the research agent and the public site. One deployment creates a
resource group with everything below; the agent job runs on a schedule, writes
verified data to storage, and opens a pull request that publishes the site.

| Resource | Purpose | Approx. cost |
|---|---|---|
| Managed identity | The agent's only credential. No keys anywhere. | free |
| Storage (LRS, versioned) | `sources` (raw copy of every source, so each claim traces to exact bytes), `claims`, `site-data`, `runs` | under $1/mo |
| Key Vault (RBAC) | GitHub token; optional Anthropic or web-search API keys | cents/mo |
| Log Analytics + App Insights | Run logs and cost tracking, with a daily ingestion cap | free at the default cap |
| Microsoft Foundry + Claude deployments | Entra ID only (`disableLocalAuth: true`) | pay per token only |
| Container Apps job (consumption) | The agent. Scales to zero between runs | typically within the monthly free grant |
| Static Web App (Free) | The public site; GitHub Actions deploys to it | free |
| Container Registry | **Optional, off by default** — use GitHub Container Registry instead | ~$5/mo if enabled |
| Budget | Email alerts at 50/80/100% actual and 100% forecast | free |

Azure prices are approximate list prices; check the Azure pricing calculator for your region.

```
infra/
├── main.bicep                  subscription-scope entry point
├── modules/                    one module per resource
└── params/
    ├── minimal.bicepparam      (lowest cost; start here)
    ├── lean.bicepparam
    ├── balanced.bicepparam
    └── deep.bicepparam
```

---

## Before you deploy: check Claude-in-Foundry eligibility

Claude in Foundry is billed pay-as-you-go through Azure Marketplace in Claude
Consumption Units (CCU), at Anthropic's published per-model token rates.
Microsoft's hosting comparison excludes **free trial, student, credit-based,
South Korea enterprise and CSP subscriptions**. A regular paid subscription
with a billing address in a country Anthropic supports should qualify.

Check your subscription's offer type (Portal → Subscriptions → your
subscription → Overview → *Offer*), then confirm the models are offered in
your region:

```bash
az cognitiveservices model list --location eastus2 \
  --query "[?model.format=='Anthropic'].{name:model.name, version:model.version}" -o table
```

- **Models listed** → use `llmBackend = 'foundry'` (the default). Make sure the
  model IDs in your param file match the list exactly.
- **Nothing listed, or deployment fails with a Marketplace eligibility error** →
  set `llmBackend = 'anthropic'` and pass an Anthropic API key at deploy time
  (see below). Nothing else changes; the agent uses the same SDK either way.

**Terms:** deploying Claude through Foundry auto-accepts the Anthropic
Marketplace offer using `claudeOrganizationName`, `claudeCountryCode` and
`claudeIndustry`. Set these to your real legal entity, and read the
[Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
and [Usage Policy](https://www.anthropic.com/legal/aup) first.

---

## Deploy

1. Pick a tier and fill in the five values at the top of its param file
   (`claudeOrganizationName`, `budgetAlertEmails`, `deployerPrincipalId`,
   `apiContactEmail`, `githubRepo`). Get your object ID with:

   ```bash
   az ad signed-in-user show --query id -o tsv
   ```

2. Preview, then deploy:

   ```bash
   az login
   az account set --subscription "<subscription name or id>"

   az deployment sub what-if  --location eastus2 \
     --template-file main.bicep --parameters params/balanced.bicepparam

   az deployment sub create --name hcatlas-infra --location eastus2 \
     --template-file main.bicep --parameters params/balanced.bicepparam
   ```

   Claude deployments can take several minutes. If ARM reports a
   `GatewayTimeout` on a model deployment, it is usually still finishing —
   check before re-running:

   ```bash
   az cognitiveservices account deployment list -g rg-hcatlas-prod -n <foundry account> -o table
   ```

3. **Secrets.** Add them now with the deploy command (the job only references
   secrets that exist):

   ```bash
   az deployment sub create ... --parameters params/balanced.bicepparam \
     githubToken="<fine-grained PAT>" \
     anthropicApiKey="<only if llmBackend=anthropic>"
   ```

   GitHub token: a fine-grained personal access token scoped to the one repo,
   with **Contents: read/write** and **Pull requests: read/write**.

4. **Connect the site to GitHub Actions.** Get the deployment token and add it
   to the repo as the secret `AZURE_STATIC_WEB_APPS_API_TOKEN`:

   ```bash
   az staticwebapp secrets list -n swa-hcatlas-prod -g rg-hcatlas-prod \
     --query properties.apiKey -o tsv
   ```

   Pull requests then get preview URLs automatically; merging publishes.

5. **Run the agent on demand** (for the initial build, or to test):

   ```bash
   az containerapp job start -n job-hcatlas-prod-agent -g rg-hcatlas-prod
   ```

   Until the agent image exists, the job runs a Microsoft placeholder container.
   Update `agentImage` in the param file and redeploy once it's built.

Switching tiers later is just redeploying with another param file.

---

## Cost options

The infrastructure costs roughly **$1–3/month in every tier**. Almost all
of the spend is Claude tokens, and that depends on which model does each
stage of the pipeline:

| Stage | What it does |
|---|---|
| Screen | Reads abstracts from free scholarly APIs and picks relevant studies |
| Extract | Pulls claims from sources, each with a **verbatim quote and location** |
| Verify | Code first confirms each quote exists in the cached source (free); then a model checks the quote actually supports the claim |
| Synthesize | Writes each country's profile from verified claims only |

Structured data (WHO, World Bank, OECD) and literature search (OpenAlex,
PubMed, Europe PMC, Crossref) come from free APIs, so they add no model cost.

| | **Minimal** (start here) | **Lean** | **Balanced** | **Deep** |
|---|---|---|---|---|
| Screen / Extract | Haiku / Haiku | Haiku / Haiku | Haiku / Sonnet | Haiku / Sonnet |
| Verify / Synthesize | Haiku + Sonnet spot-check / Haiku | Sonnet / Haiku | Sonnet / Sonnet | Opus / Opus |
| Refresh | Twice a year | Quarterly | Monthly | Weekly check for changed sources |
| Est. per country, full pass | ~$0.15–0.25 | ~$0.50–1 | ~$2–3 | ~$3–5 |
| First wave, 15 countries | ~$3–5 | ~$8–15 | ~$30–45 | ~$45–75 |
| All ~60 countries | ~$10–15 | ~$30–60 | ~$120–180 | ~$180–300 |
| Ongoing per month | ~$1–3 | ~$3–8 | ~$15–30 | ~$40–70 |
| Budget alert set to | $10 | $25 | $60 | $125 |

### How the Minimal tier stays cheap

- **Code does most of the fact-checking.** Every extracted claim must carry a
  verbatim quote; code confirms the quote exists in the cached source before
  any model sees it. Haiku then checks the quote supports the claim, and
  Sonnet re-checks a random ~10% sample as quality control. Disagreements
  send that country back for a Sonnet pass.
- **Read less.** Long reports (the European Observatory reviews run 200+
  pages) are split by section and only the relevant chapters are sent,
  cutting input tokens by more than half.
- **Prompt caching.** Instructions, the output schema and each source document
  are cached, so repeat questions against the same document are billed at a
  fraction of the normal input price.
- **Only changed sources are re-read.** Each refresh compares source hashes and
  pulls updated statistics from free APIs; unchanged countries cost nothing.
- **Grow in waves.** Start with ~15 countries plus the US baseline; add the
  rest as budget allows.

Estimates use Anthropic list prices per million tokens (input/output):
Haiku 5.5 $0.10/$0.50 for prompts under 100k tokens, Sonnet 5.5 $2/$10,
Opus 5.5 $4/$20. Foundry bills Claude at Anthropic's published rates,
converted to CCU. Keep each Haiku prompt under 100k tokens: above that,
Haiku 5.5 is priced at $0.50/$2.50. Refresh runs only re-process countries
whose sources changed.

**Hosting version:** deployments default to version `2` (hosted on Azure:
prompts and outputs stay in Azure, Data Zone US available). Version `1` is
hosted on Anthropic's infrastructure and adds the `/files` and `/skills`
APIs, which this agent doesn't need.

**Keeping the initial build cheap:** run it manually in batches
(`az containerapp job start`) over a few weeks rather than at once. The
`countriesPerRun` setting caps each run, and the agent resumes where it
stopped. Budget alerts warn you; they don't stop spending, so the agent also
enforces its own per-run token ceiling.

**Web search:** the Bing Search API was retired in August 2025, and its
replacement (Grounding with Bing) returns AI answers rather than raw results,
which doesn't suit citation-grade work. The agent relies on free scholarly
APIs plus a curated list of official sources. If broader web search is needed
later, add a search provider's key as `webSearchApiKey`.

---

## Security notes

- No API keys exist for Foundry or Storage: both are Entra ID only.
- The agent identity has only Blob Data Contributor (one account), Key Vault
  Secrets User (one vault) and Cognitive Services User (one Foundry account).
- `deployerPrincipalId` gives you secret management and model access for local
  testing; leave it empty to skip.

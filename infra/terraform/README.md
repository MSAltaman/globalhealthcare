# Terraform: the atlas on Google Cloud

This folder defines every piece of the atlas's Google Cloud infrastructure as
code. It replaces the Azure Bicep in `infra/` once production runs on Google
Cloud. The architecture it implements is described on the architecture page
(stages 1-5 plus the shared band).

**The rule:** Terraform builds the containers; the deployment pipeline fills
them. Terraform creates the BigQuery datasets, the hosting site, the service
accounts and the alerts. The pipeline loads tables into those datasets and
uploads the website files. Never put data or site content in Terraform, and
never create infrastructure by hand in the console.

## Layout

```
infra/terraform/
  bootstrap/         run once by hand: state bucket, GitHub sign-in, Terraform's accounts, budget
  modules/
    services/        turns on Google Cloud APIs
    identity/        the pipeline's "deployer" account (loads data, publishes the site)
    bigquery/        datasets and who can read or write them
    hosting/         Firebase Hosting site and custom domain
    dns/             records in your existing Cloud DNS zone
    monitoring/      where alerts are sent
    agent/           the research agent on Cloud Run (off until you switch it on)
    atlas/           one whole environment, assembled from the modules above
  envs/
    staging/         calls modules/atlas with staging settings
    prod/            calls modules/atlas with production settings
```

Staging and production run the same `modules/atlas` code with different
settings, so staging is a true rehearsal of production.

## Coming from Bicep

| Bicep | Terraform |
|---|---|
| `resource` | `resource` |
| `module` | `module` (a folder of `.tf` files) |
| `param` | `variable` |
| `output` | `output` |
| `.bicepparam` file | `terraform.tfvars` file |
| `az deployment group what-if` | `terraform plan` |
| `az deployment group create` | `terraform apply` |
| Azure tracks what was deployed | **Terraform keeps its own record: the state file** |

**State** is the one genuinely new idea. Terraform compares three things: your
code, its state file (what it believes it created), and what actually exists.
`plan` shows the difference; `apply` makes reality match the code and updates
the state. Protect the state: it lives in a versioned bucket, only the
pipeline writes it, and nobody edits it by hand. If something was changed in
the console, the next `plan` reports it as drift.

Other things you will meet:
- **Providers** are plugins that talk to an API (`google`, `google-beta` for
  Firebase). `.terraform.lock.hcl` pins their exact versions; commit it.
- **`count` and `for_each`** create zero, one or many copies of a resource.
  `count = var.enable_research_agent ? 1 : 0` is how the agent stays off.
- **`depends_on`** forces order when Terraform can't see a dependency, such as
  an API that must be on before a resource can be created.
- **`terraform fmt`** formats the code; the pipeline fails if it isn't formatted.

## One-time setup

You need the `gcloud` CLI and Terraform 1.9 or newer
(on a Mac: `brew tap hashicorp/tap && brew install hashicorp/tap/terraform`;
plain `brew install terraform` gives an old 1.5.x build, because Homebrew's own
formula stopped updating after HashiCorp's 2023 license change).

1. **Create the two projects and link billing.** In the console or:
   ```sh
   gcloud projects create healthcare-atlas-staging
   gcloud projects create healthcare-atlas-prod
   gcloud billing projects link healthcare-atlas-staging --billing-account=XXXXXX-XXXXXX-XXXXXX
   gcloud billing projects link healthcare-atlas-prod --billing-account=XXXXXX-XXXXXX-XXXXXX
   ```
   Project ids are global: if one is taken, pick another and use it everywhere below.
2. **Run bootstrap with your own login.**
   ```sh
   gcloud auth application-default login
   cd infra/terraform/bootstrap
   cp terraform.tfvars.example terraform.tfvars   # fill in; this file is ignored by git
   terraform init
   terraform plan      # read it: everything should be "to add"
   terraform apply
   terraform output github_variables
   ```
   Keep `bootstrap/terraform.tfstate` somewhere safe (it is ignored by git).
3. **Give GitHub the outputs.** In the repository: Settings > Secrets and
   variables > Actions.
   - Variables: every entry of `github_variables` (GCP_WIF_PROVIDER, TF_STATE_BUCKET, TF_SA_STAGING, TF_SA_PROD, TF_PLAN_SA_PROD, GCP_PROJECT_STAGING, GCP_PROJECT_PROD, GCP_POOL_NAME).
   - Secret: `ALERT_EMAIL`, the address for alerts. It stays out of the code.
4. **Require your approval for production.** Settings > Environments >
   `production` > Required reviewers: add yourself.
5. **Set the site ids.** `envs/*/terraform.tfvars` use `healthcare-atlas` and
   `healthcare-atlas-staging`. Firebase site ids are global; change them if taken.
6. **Merge a change under `infra/terraform/`.** The pipeline applies staging,
   then waits for your approval to apply production.

## Day to day

- Change infrastructure only through a pull request that edits these files.
- The pull request shows a plan for staging and production as a comment.
  Read the summary line ("Plan: 2 to add, 1 to change, 0 to destroy"); any
  "destroy" deserves a careful look.
- Merge: staging applies automatically; production waits for you.
- Mondays: a scheduled plan checks both environments. If someone changed
  something outside Terraform, the run fails and GitHub emails you.

## Custom domain

1. In `envs/prod/terraform.tfvars`, set `custom_domain` (for example
   `atlas.example.org`) and merge.
2. After production applies, the output `custom_domain_dns_updates` lists the
   records Firebase needs.
3. Put those records in the `dns` block in the same file (zone name and the
   project that holds your domain's Cloud DNS zone) and merge again. Firebase
   issues the SSL certificate once the records resolve.

## Turning on the research agent (later)

Set `enable_research_agent = true` in `envs/prod/terraform.tfvars`. Terraform
then creates the Artifact Registry repository, the secret slot, the source
cache bucket (files deleted after 7 days), the Cloud Run job, its hourly
schedule, and an alert on failed runs. Before the first run: push the agent
image, and add the GitHub app key with
`gcloud secrets versions add github-app-private-key --data-file=key.pem`,
so the key never passes through Terraform or its state.

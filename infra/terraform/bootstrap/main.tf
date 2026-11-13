# Bootstrap: the one piece you run by hand, once, with your own Google login.
#
# It creates what the pipeline needs before the pipeline can run:
#   - the bucket that stores Terraform state for the two environments
#   - keyless sign-in from GitHub Actions (Workload Identity Federation)
#   - the service accounts the pipeline acts as
#   - a budget with email alerts (needs billing-account rights, which the pipeline does not get)
#
# Its own state lives in a local file (terraform.tfstate in this folder, ignored by git).
# Keep that file safe, or move it into the bucket afterwards (see README.md).

locals {
  projects = {
    staging = var.staging_project_id
    prod    = var.prod_project_id
  }
  # APIs both projects need before anything else can be created.
  bootstrap_apis = [
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "storage.googleapis.com",
  ]
  project_apis = { for pair in setproduct(keys(local.projects), local.bootstrap_apis) :
  "${pair[0]}/${pair[1]}" => { project = local.projects[pair[0]], api = pair[1] } }
}

resource "google_project_service" "bootstrap" {
  for_each           = local.project_apis
  project            = each.value.project
  service            = each.value.api
  disable_on_destroy = false # turning an API off can break things that depend on it; never do it automatically
}

resource "google_project_service" "budgets" {
  project            = var.prod_project_id
  service            = "billingbudgets.googleapis.com"
  disable_on_destroy = false
}

data "google_project" "prod" {
  project_id = var.prod_project_id
}

data "google_project" "staging" {
  project_id = var.staging_project_id
}

# ---------------------------------------------------------------------------
# Terraform state bucket. Versioning keeps every earlier copy of the state, so
# a bad apply can always be traced and recovered.
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "tfstate" {
  project                     = var.prod_project_id
  name                        = "${var.prod_project_id}-tfstate"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 20 # keep the 20 most recent copies of each state file
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.bootstrap]
}

# ---------------------------------------------------------------------------
# Workload Identity Federation: GitHub Actions proves who it is with a
# short-lived token, and Google trusts it only for this one repository.
# No service account keys exist anywhere.
# ---------------------------------------------------------------------------
resource "google_iam_workload_identity_pool" "github" {
  project                   = var.prod_project_id
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.bootstrap]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.prod_project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  # Copy claims from GitHub's token into attributes we can grant access on.
  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.repository"  = "assertion.repository"
    "attribute.ref"         = "assertion.ref"
    "attribute.environment" = "assertion.environment"
  }

  # Reject tokens from any other repository outright.
  attribute_condition = "assertion.repository == \"${var.github_repository}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

locals {
  pool = google_iam_workload_identity_pool.github.name
  # Any workflow run in the repository (pull requests, staging).
  repo_principal = "principalSet://iam.googleapis.com/${local.pool}/attribute.repository/${var.github_repository}"
  # Only jobs running in the GitHub environment named "production", which requires your approval.
  prod_principal = "principalSet://iam.googleapis.com/${local.pool}/attribute.environment/production"
}

# ---------------------------------------------------------------------------
# Service accounts the pipeline acts as.
#   terraform@<staging>   applies infrastructure to staging
#   terraform@<prod>      applies infrastructure to production (production environment only)
#   tf-plan@<prod>        read-only, so pull requests can show a production plan without approval
# ---------------------------------------------------------------------------
resource "google_service_account" "terraform" {
  for_each     = local.projects
  project      = each.value
  account_id   = "terraform"
  display_name = "Terraform (${each.key})"
  depends_on   = [google_project_service.bootstrap]
}

# Terraform creates projects' resources and their permissions, which needs broad rights.
# Owner is limited to one project each, and only the pipeline can act as these accounts.
resource "google_project_iam_member" "terraform_owner" {
  for_each = local.projects
  project  = each.value
  role     = "roles/owner"
  member   = "serviceAccount:${google_service_account.terraform[each.key].email}"
}

resource "google_storage_bucket_iam_member" "terraform_state" {
  for_each = local.projects
  bucket   = google_storage_bucket.tfstate.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${google_service_account.terraform[each.key].email}"
}

resource "google_service_account_iam_member" "terraform_wif" {
  for_each           = local.projects
  service_account_id = google_service_account.terraform[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.key == "prod" ? local.prod_principal : local.repo_principal
}

resource "google_service_account" "tf_plan" {
  project      = var.prod_project_id
  account_id   = "tf-plan"
  display_name = "Terraform plan (read-only, production)"
  depends_on   = [google_project_service.bootstrap]
}

resource "google_project_iam_member" "tf_plan" {
  for_each = toset(["roles/viewer", "roles/iam.securityReviewer", "roles/firebase.viewer"])
  project  = var.prod_project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.tf_plan.email}"
}

resource "google_storage_bucket_iam_member" "tf_plan_state" {
  bucket = google_storage_bucket.tfstate.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.tf_plan.email}"
}

resource "google_service_account_iam_member" "tf_plan_wif" {
  service_account_id = google_service_account.tf_plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.repo_principal
}

# ---------------------------------------------------------------------------
# Budget across both projects, with email alerts at 50%, 90% and 100%.
# ---------------------------------------------------------------------------
resource "google_billing_budget" "atlas" {
  billing_account = var.billing_account_id
  display_name    = "Healthcare Atlas"

  budget_filter {
    # The Budgets API stores projects by number, not id. Writing numbers here
    # matches what it returns, so plans don't show a change that never settles.
    projects = [
      "projects/${data.google_project.staging.number}",
      "projects/${data.google_project.prod.number}",
    ]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }

  # With no notification rule, alert emails go to the billing account's admins (you).

  depends_on = [google_project_service.budgets]
}

# The "deployer" service account: what the pipeline acts as when it loads data
# into BigQuery and publishes the website. It cannot change infrastructure;
# only Terraform's own account can.

variable "project_id" {
  type = string
}

variable "env" {
  type = string
}

variable "wif_principal" {
  description = "Who may act as the deployer: a principalSet from the GitHub sign-in pool."
  type        = string
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "deployer"
  display_name = "Pipeline deployer (${var.env})"
}

# Run BigQuery load and query jobs, and publish to Firebase Hosting.
# Write access to specific datasets is granted in the bigquery module.
resource "google_project_iam_member" "deployer" {
  for_each = toset(["roles/bigquery.jobUser", "roles/firebasehosting.admin"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = var.wif_principal
}

output "deployer_email" {
  value = google_service_account.deployer.email
}

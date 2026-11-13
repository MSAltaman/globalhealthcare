# Copy these into GitHub: Settings > Secrets and variables > Actions > Variables.
# None of them is a secret; they are names, not credentials.

output "github_variables" {
  description = "Repository variables the Terraform and deploy workflows read."
  value = {
    GCP_WIF_PROVIDER    = google_iam_workload_identity_pool_provider.github.name
    TF_STATE_BUCKET     = google_storage_bucket.tfstate.name
    TF_SA_STAGING       = google_service_account.terraform["staging"].email
    TF_SA_PROD          = google_service_account.terraform["prod"].email
    TF_PLAN_SA_PROD     = google_service_account.tf_plan.email
    GCP_PROJECT_STAGING = var.staging_project_id
    GCP_PROJECT_PROD    = var.prod_project_id
    GCP_POOL_NAME       = google_iam_workload_identity_pool.github.name
  }
}

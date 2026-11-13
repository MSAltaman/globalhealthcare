variable "staging_project_id" {
  description = "Google Cloud project for staging, created by hand (e.g. healthcare-atlas-staging)."
  type        = string
}

variable "prod_project_id" {
  description = "Google Cloud project for production, created by hand (e.g. healthcare-atlas-prod). Also holds the state bucket and the GitHub sign-in pool."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account both projects are linked to, as shown in the console (XXXXXX-XXXXXX-XXXXXX)."
  type        = string
}

variable "github_repository" {
  description = "The only GitHub repository allowed to sign in."
  type        = string
  default     = "MSAltaman/globalhealthcare"
}

variable "region" {
  description = "Region for the state bucket."
  type        = string
  default     = "us-central1"
}

variable "monthly_budget_usd" {
  description = "Monthly spending level that triggers the email alerts. Alerts only; nothing is shut off."
  type        = number
  default     = 10
}

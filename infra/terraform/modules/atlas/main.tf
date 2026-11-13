# One environment of the atlas, assembled from the smaller modules.
# envs/staging and envs/prod both call this module; only their settings differ,
# so staging is an exact rehearsal of production.

terraform {
  required_providers {
    google      = { source = "hashicorp/google" }
    google-beta = { source = "hashicorp/google-beta" }
  }
}

variable "env" {
  description = "staging or prod"
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.env)
    error_message = "env must be staging or prod."
  }
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "wif_pool_name" {
  description = "Full name of the GitHub sign-in pool created by bootstrap (GCP_POOL_NAME)."
  type        = string
}

variable "github_repository" {
  type    = string
  default = "MSAltaman/globalhealthcare"
}

variable "site_id" {
  type = string
}

variable "custom_domain" {
  type    = string
  default = ""
}

variable "dns" {
  description = "Optional: existing Cloud DNS zone and the records to add for the custom domain."
  type = object({
    project_id = string
    zone_name  = string
    records = list(object({
      name    = string
      type    = string
      ttl     = optional(number, 300)
      rrdatas = list(string)
    }))
  })
  default = null
}

variable "bigquery_readers" {
  type    = list(string)
  default = []
}

variable "alert_email" {
  type      = string
  sensitive = true
}

variable "enable_research_agent" {
  description = "Create the research agent's Cloud Run job and schedule. Leave off until the agent moves here from Claude scheduled tasks."
  type        = bool
  default     = false
}

locals {
  labels = { app = "healthcare-atlas", env = var.env, managed-by = "terraform" }

  apis = concat([
    "bigquery.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "dns.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    ], var.enable_research_agent ? [
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "aiplatform.googleapis.com",
  ] : [])

  # Production deploys only from jobs in the GitHub "production" environment (your approval);
  # staging from any workflow in the repository.
  deployer_principal = var.env == "prod" ? "principalSet://iam.googleapis.com/${var.wif_pool_name}/attribute.environment/production" : "principalSet://iam.googleapis.com/${var.wif_pool_name}/attribute.repository/${var.github_repository}"
}

module "services" {
  source     = "../services"
  project_id = var.project_id
  apis       = local.apis
}

module "identity" {
  source        = "../identity"
  project_id    = var.project_id
  env           = var.env
  wif_principal = local.deployer_principal
  depends_on    = [module.services]
}

module "bigquery" {
  source              = "../bigquery"
  project_id          = var.project_id
  dataset_id          = var.env == "prod" ? "atlas" : "atlas_staging"
  create_test_dataset = var.env == "staging"
  writer              = module.identity.deployer_email
  readers             = var.bigquery_readers
  labels              = local.labels
  depends_on          = [module.services]
}

module "hosting" {
  source        = "../hosting"
  project_id    = var.project_id
  site_id       = var.site_id
  custom_domain = var.custom_domain
  depends_on    = [module.services]
}

module "dns" {
  source     = "../dns"
  count      = var.dns == null ? 0 : 1
  project_id = var.dns.project_id
  zone_name  = var.dns.zone_name
  records    = var.dns.records
}

module "monitoring" {
  source      = "../monitoring"
  project_id  = var.project_id
  alert_email = var.alert_email
  depends_on  = [module.services]
}

module "agent" {
  source                  = "../agent"
  count                   = var.enable_research_agent ? 1 : 0
  project_id              = var.project_id
  region                  = var.region
  notification_channel_id = module.monitoring.channel_id
  depends_on              = [module.services]
}

output "site_url" {
  value = module.hosting.default_url
}

output "bigquery_dataset" {
  value = "${var.project_id}.${module.bigquery.dataset_id}"
}

output "deployer_email" {
  value = module.identity.deployer_email
}

output "custom_domain_dns_updates" {
  value = module.hosting.required_dns_updates
}

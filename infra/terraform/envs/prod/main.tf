# The prod environment. Settings only; the resources are defined in modules/atlas.

terraform {
  required_version = ">= 1.9"

  required_providers {
    google      = { source = "hashicorp/google", version = "~> 8.0" }
    google-beta = { source = "hashicorp/google-beta", version = "~> 8.0" }
  }

  # State lives in the bucket bootstrap created. The bucket name is passed at
  # init time: terraform init -backend-config="bucket=<TF_STATE_BUCKET>"
  backend "gcs" {
    prefix = "atlas/prod"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

module "atlas" {
  source                = "../../modules/atlas"
  env                   = "prod"
  project_id            = var.project_id
  region                = var.region
  wif_pool_name         = var.wif_pool_name
  site_id               = var.site_id
  custom_domain         = var.custom_domain
  dns                   = var.dns
  bigquery_readers      = var.bigquery_readers
  alert_email           = var.alert_email
  enable_research_agent = var.enable_research_agent
}

output "site_url" {
  value = module.atlas.site_url
}

output "bigquery_dataset" {
  value = module.atlas.bigquery_dataset
}

output "deployer_email" {
  value = module.atlas.deployer_email
}

output "custom_domain_dns_updates" {
  value = module.atlas.custom_domain_dns_updates
}

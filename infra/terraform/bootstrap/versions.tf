terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }
}

# Uses your own login: run `gcloud auth application-default login` first.
# user_project_override sends API quota and billing checks to the prod project,
# which the budget API needs when called with user credentials.
provider "google" {
  region                = var.region
  billing_project       = var.prod_project_id
  user_project_override = true
}

# Firebase Hosting for the static site. Terraform creates the site and its
# custom domain; the pipeline uploads the files (with the Firebase CLI) and
# promotes them from staging to live.
#
# Firebase resources are only in the google-beta provider.

terraform {
  required_providers {
    google-beta = {
      source = "hashicorp/google-beta"
    }
  }
}

variable "project_id" {
  type = string
}

variable "site_id" {
  description = "Globally unique; becomes <site_id>.web.app."
  type        = string
}

variable "custom_domain" {
  description = "Optional, e.g. atlas.example.org. Leave empty for staging."
  type        = string
  default     = ""
}

resource "google_firebase_project" "this" {
  provider = google-beta
  project  = var.project_id
}

resource "google_firebase_hosting_site" "atlas" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.site_id

  depends_on = [google_firebase_project.this]
}

resource "google_firebase_hosting_custom_domain" "atlas" {
  count         = var.custom_domain == "" ? 0 : 1
  provider      = google-beta
  project       = var.project_id
  site_id       = google_firebase_hosting_site.atlas.site_id
  custom_domain = var.custom_domain

  # Don't block the apply waiting for DNS; Firebase finishes setup once the records exist.
  wait_dns_verification = false
}

output "default_url" {
  value = google_firebase_hosting_site.atlas.default_url
}

output "site_id" {
  value = google_firebase_hosting_site.atlas.site_id
}

output "required_dns_updates" {
  description = "Records Firebase needs for the custom domain. Copy them into dns_records (see README)."
  value       = try(google_firebase_hosting_custom_domain.atlas[0].required_dns_updates, null)
}

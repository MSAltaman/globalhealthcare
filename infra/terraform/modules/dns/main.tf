# DNS records in the Cloud DNS zone that already holds your domain
# (registering a domain in Google Cloud creates that zone). This module only
# adds records; it never creates or deletes the zone itself.

variable "project_id" {
  description = "Project that holds the existing Cloud DNS zone."
  type        = string
}

variable "zone_name" {
  description = "Name of the existing managed zone (not the domain), e.g. example-org."
  type        = string
}

variable "records" {
  description = "Records to add. name must end with a dot, e.g. atlas.example.org."
  type = list(object({
    name    = string
    type    = string
    ttl     = optional(number, 300)
    rrdatas = list(string)
  }))
  default = []
}

data "google_dns_managed_zone" "zone" {
  project = var.project_id
  name    = var.zone_name
}

resource "google_dns_record_set" "this" {
  for_each     = { for r in var.records : "${r.name}/${r.type}" => r }
  project      = var.project_id
  managed_zone = data.google_dns_managed_zone.zone.name
  name         = each.value.name
  type         = each.value.type
  ttl          = each.value.ttl
  rrdatas      = each.value.rrdatas
}

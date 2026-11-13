# Turns on the Google Cloud APIs an environment uses.
# Every other module depends on this one, so APIs exist before resources are created.

variable "project_id" {
  type = string
}

variable "apis" {
  description = "APIs to enable."
  type        = list(string)
}

resource "google_project_service" "this" {
  for_each           = toset(var.apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

output "enabled" {
  description = "Enabled APIs; other modules wait on this."
  value       = [for s in google_project_service.this : s.service]
}

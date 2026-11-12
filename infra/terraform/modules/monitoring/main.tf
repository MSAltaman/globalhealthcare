# Where alerts go. The budget alert is set up in bootstrap; this channel is for
# alert policies on running services (the research agent's job, later).

variable "project_id" {
  type = string
}

variable "alert_email" {
  description = "Email for alerts. Passed in from a GitHub secret, never written in the code."
  type        = string
  sensitive   = true
}

resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "Atlas alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

output "channel_id" {
  value = google_monitoring_notification_channel.email.id
}

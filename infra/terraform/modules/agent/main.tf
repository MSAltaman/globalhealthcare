# The research agent on Google Cloud: the final step, replacing the Claude
# scheduled task. Off by default (enable_research_agent = false), so nothing
# here exists until you switch it on.
#
#   Cloud Scheduler --(hourly)--> Cloud Run job (container from Artifact Registry)
#                                  |-- Claude on Vertex AI
#                                  |-- GitHub app key from Secret Manager
#                                  '-- source-text cache in Cloud Storage (auto-deleted)

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "image_tag" {
  description = "Agent image tag in Artifact Registry. The pipeline pushes images; Terraform only points the job at one."
  type        = string
  default     = "latest"
}

variable "schedule" {
  description = "Cron schedule for research runs."
  type        = string
  default     = "3 * * * *"
}

variable "time_zone" {
  type    = string
  default = "America/Chicago"
}

variable "notification_channel_id" {
  type = string
}

resource "google_artifact_registry_repository" "agent" {
  project       = var.project_id
  location      = var.region
  repository_id = "atlas"
  format        = "DOCKER"
  description   = "Research agent images"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
}

# Secret slot only. You add the value once with `gcloud secrets versions add`,
# so the key never passes through Terraform or its state.
resource "google_secret_manager_secret" "github_app_key" {
  project   = var.project_id
  secret_id = "github-app-private-key"
  replication {
    auto {}
  }
}

resource "google_storage_bucket" "source_cache" {
  project                     = var.project_id
  name                        = "${var.project_id}-source-cache"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Source documents are kept only long enough to check passages, then deleted.
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_service_account" "agent" {
  project      = var.project_id
  account_id   = "research-agent"
  display_name = "Research agent"
}

resource "google_project_iam_member" "agent" {
  for_each = toset(["roles/aiplatform.user", "roles/logging.logWriter"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_secret_manager_secret_iam_member" "agent" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.github_app_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_storage_bucket_iam_member" "agent" {
  bucket = google_storage_bucket.source_cache.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_cloud_run_v2_job" "agent" {
  project             = var.project_id
  name                = "research-agent"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.agent.email
      timeout         = "3000s" # 50 minutes, so a run ends before the next one starts
      max_retries     = 0       # a failed run is picked up by the next scheduled run
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agent.repository_id}/research-agent:${var.image_tag}"
        resources {
          limits = { cpu = "1", memory = "2Gi" }
        }
        env {
          name  = "SOURCE_CACHE_BUCKET"
          value = google_storage_bucket.source_cache.name
        }
        env {
          name = "GITHUB_APP_PRIVATE_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.github_app_key.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

# Scheduler needs its own identity allowed to start the job.
resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "agent-scheduler"
  display_name = "Starts research agent runs"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.agent.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "agent" {
  project   = var.project_id
  region    = var.region
  name      = "research-agent"
  schedule  = var.schedule
  time_zone = var.time_zone

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.agent.name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Email when a run logs an error.
resource "google_monitoring_alert_policy" "agent_errors" {
  project      = var.project_id
  display_name = "Research agent run failed"
  combiner     = "OR"

  conditions {
    display_name = "Error in research agent logs"
    condition_matched_log {
      filter = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${google_cloud_run_v2_job.agent.name}\" AND severity>=ERROR"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "3600s" # at most one email an hour
    }
  }

  notification_channels = [var.notification_channel_id]
}

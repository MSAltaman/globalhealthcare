# BigQuery datasets. Terraform creates the datasets and decides who can use them;
# the pipeline's loader creates and refills the tables and views inside them
# from the GitHub data on every release.

variable "project_id" {
  type = string
}

variable "location" {
  type    = string
  default = "US"
}

variable "dataset_id" {
  description = "Main dataset: atlas_staging or atlas."
  type        = string
}

variable "create_test_dataset" {
  description = "Also create atlas_ci, where pull-request tests load data; its tables delete themselves after a day."
  type        = bool
  default     = false
}

variable "writer" {
  description = "Service account email allowed to write tables (the pipeline deployer)."
  type        = string
}

variable "readers" {
  description = "People or groups who may query, e.g. [\"user:name@example.com\"]."
  type        = list(string)
  default     = []
}

variable "labels" {
  type    = map(string)
  default = {}
}

resource "google_bigquery_dataset" "main" {
  project       = var.project_id
  dataset_id    = var.dataset_id
  friendly_name = "Global Healthcare Atlas"
  description   = "Rebuilt from the GitHub repository on every release. Do not edit by hand: changes are overwritten."
  location      = var.location
  labels        = var.labels

  # Refuse to delete a dataset that still has tables, so a mistaken plan cannot wipe it.
  delete_contents_on_destroy = false
}

resource "google_bigquery_dataset" "ci" {
  count                       = var.create_test_dataset ? 1 : 0
  project                     = var.project_id
  dataset_id                  = "atlas_ci"
  friendly_name               = "Atlas pull-request tests"
  description                 = "Scratch space for pipeline tests. Tables expire after 24 hours."
  location                    = var.location
  labels                      = var.labels
  default_table_expiration_ms = 24 * 60 * 60 * 1000
  delete_contents_on_destroy  = true
}

locals {
  datasets = concat([google_bigquery_dataset.main.dataset_id], [for d in google_bigquery_dataset.ci : d.dataset_id])
}

resource "google_bigquery_dataset_iam_member" "writer" {
  for_each   = toset(local.datasets)
  project    = var.project_id
  dataset_id = each.value
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.writer}"
}

resource "google_bigquery_dataset_iam_member" "readers" {
  for_each   = toset(var.readers)
  project    = var.project_id
  dataset_id = google_bigquery_dataset.main.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = each.value
}

# Readers also need to run query jobs in the project.
resource "google_project_iam_member" "readers_jobs" {
  for_each = toset(var.readers)
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = each.value
}

output "dataset_id" {
  value = google_bigquery_dataset.main.dataset_id
}

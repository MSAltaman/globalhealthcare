# Values come from terraform.tfvars (non-secret, committed) and from TF_VAR_*
# environment variables set by the pipeline (project id, pool name, alert email).

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "wif_pool_name" {
  type = string
}

variable "site_id" {
  type = string
}

variable "custom_domain" {
  type    = string
  default = ""
}

variable "dns" {
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
  type    = bool
  default = false
}

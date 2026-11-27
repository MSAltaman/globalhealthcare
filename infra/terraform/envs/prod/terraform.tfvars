# Production settings. Project id, sign-in pool and alert email come from the pipeline.
site_id               = "healthcare-atlas"
enable_research_agent = false

# The live site's address. Firebase issues the SSL certificate once the DNS
# records from the custom_domain_dns_updates output are in place. Those records
# go into the johnbojanski.com zone by hand (it lives in another project), so
# the dns block below stays unused.
custom_domain = "healthcare.johnbojanski.com"

# To let Terraform manage the records instead:
# dns = {
#   project_id = "project-that-holds-the-zone"
#   zone_name  = "example-org"
#   records    = [] # fill from the custom_domain_dns_updates output after the first apply
# }

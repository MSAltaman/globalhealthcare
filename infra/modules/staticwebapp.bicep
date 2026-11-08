// The public site. Not linked to a repo here: GitHub Actions deploys to it with
// the deployment token (see README), which keeps the PR-preview workflow you
// control in the repo rather than in Azure.
param name string
param location string
param tags object
@allowed([
  'Free'
  'Standard'
])
param sku string

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    stagingEnvironmentPolicy: 'Enabled'
    allowConfigFileUpdates: true
  }
}

output name string = swa.name
output defaultHostname string = swa.properties.defaultHostname

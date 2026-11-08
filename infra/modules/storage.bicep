// Storage for the research pipeline. Shared-key access is disabled; the agent
// reaches it with its managed identity only.
//
// Containers
//   sources    raw copies of every fetched source (PDF/HTML/API JSON) + hash, so
//              every published claim can be traced to the exact bytes it came from
//   claims     extracted, verified claim records (JSON) per country
//   site-data  the JSON the static site renders from
//   runs       per-run manifests, cost logs and verification reports
param name string
param location string
param tags object
param agentPrincipalId string
param deployerPrincipalId string = ''

var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource sa 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    defaultToOAuthAuthentication: true
  }
}

resource blobSvc 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: sa
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: {
      enabled: true
      days: 14
    }
  }
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for c in ['sources', 'claims', 'site-data', 'runs']: {
    parent: blobSvc
    name: c
    properties: {
      publicAccess: 'None'
    }
  }
]

// Keep costs flat as the source cache grows: cached sources move to Cool after
// 30 days and old blob versions are removed after 90.
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: sa
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'sources-to-cool'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['sources/']
            }
            actions: {
              baseBlob: {
                tierToCool: {
                  daysAfterModificationGreaterThan: 30
                }
              }
            }
          }
        }
        {
          name: 'expire-old-versions'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
            }
            actions: {
              version: {
                delete: {
                  daysAfterCreationGreaterThan: 90
                }
              }
            }
          }
        }
      ]
    }
  }
}

resource agentBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sa.id, agentPrincipalId, blobDataContributor)
  scope: sa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: agentPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  name: guid(sa.id, deployerPrincipalId, blobDataContributor)
  scope: sa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

output name string = sa.name
output blobEndpoint string = sa.properties.primaryEndpoints.blob

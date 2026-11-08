// Optional private registry for the agent image. Off by default to save cost:
// a public image on GitHub Container Registry works with no registry at all.
param name string
param location string
param tags object
param agentPrincipalId string

var acrPull = '7f951dff-4ed5-480b-a42d-c4c6e3e2b7e9'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, agentPrincipalId, acrPull)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
    principalId: agentPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer

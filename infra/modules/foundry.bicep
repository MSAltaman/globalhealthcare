// Microsoft Foundry account + project + Claude deployments.
// Resource shapes follow Microsoft's official Claude-on-Foundry starter kit
// (github.com/Azure-Samples/claude, API 2025-10-01-preview).
//
// IMPORTANT: the `modelProviderData` block auto-accepts the Anthropic Azure
// Marketplace offer on your behalf. Read the Anthropic Commercial Terms and
// Usage Policy before deploying, and set the attestation values to your real
// organization. `industry` must be lowercase.
param accountName string
param projectName string
param location string
param tags object

param haikuModel string
param sonnetModel string
param opusModel string
param haikuCapacity int
param sonnetCapacity int
param opusCapacity int
param modelVersion string

param claudeOrganizationName string
param claudeCountryCode string
param claudeIndustry string

param agentPrincipalId string
param deployerPrincipalId string = ''

// Least-privilege inference role for Claude on Foundry (MaaS data path).
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'

var providerData = {
  organizationName: claudeOrganizationName
  countryCode: claudeCountryCode
  industry: claudeIndustry
}

resource account 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    // Entra ID only: no API keys exist to leak.
    disableLocalAuth: true
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-10-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// Roles first so the (slow) model deployments absorb RBAC propagation time.
resource agentRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, agentPrincipalId, cognitiveServicesUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: agentPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  name: guid(account.id, deployerPrincipalId, cognitiveServicesUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

// Foundry serializes deployments within one account, so they are chained.
resource haiku 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = if (!empty(haikuModel)) {
  parent: account
  name: haikuModel
  sku: {
    name: 'GlobalStandard'
    capacity: haikuCapacity
  }
  properties: {
    model: {
      format: 'Anthropic'
      name: haikuModel
      version: modelVersion
    }
    // Required for Claude; missing from Bicep's type data (same as Microsoft's sample).
    #disable-next-line BCP037
    modelProviderData: providerData
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
  dependsOn: [
    project
    agentRole
  ]
}

resource sonnet 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = if (!empty(sonnetModel)) {
  parent: account
  name: sonnetModel
  sku: {
    name: 'GlobalStandard'
    capacity: sonnetCapacity
  }
  properties: {
    model: {
      format: 'Anthropic'
      name: sonnetModel
      version: modelVersion
    }
    // Required for Claude; missing from Bicep's type data (same as Microsoft's sample).
    #disable-next-line BCP037
    modelProviderData: providerData
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
  dependsOn: [
    project
    agentRole
    haiku
  ]
}

resource opus 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = if (!empty(opusModel)) {
  parent: account
  name: opusModel
  sku: {
    name: 'GlobalStandard'
    capacity: opusCapacity
  }
  properties: {
    model: {
      format: 'Anthropic'
      name: opusModel
      version: modelVersion
    }
    // Required for Claude; missing from Bicep's type data (same as Microsoft's sample).
    #disable-next-line BCP037
    modelProviderData: providerData
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
  dependsOn: [
    project
    agentRole
    sonnet
  ]
}

// The Anthropic SDK appends /v1/messages to this base URL.
output claudeBaseUrl string = 'https://${account.name}.services.ai.azure.com/anthropic'
output accountName string = account.name
output projectName string = project.name
output haikuDeploymentName string = haikuModel
output sonnetDeploymentName string = sonnetModel
output opusDeploymentName string = opusModel

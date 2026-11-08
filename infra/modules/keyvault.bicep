// Key Vault (RBAC mode). Secrets are only created for values you pass in, so
// the job never references a secret that does not exist yet.
param name string
param location string
param tags object
param agentPrincipalId string
param deployerPrincipalId string = ''

@secure()
param githubToken string = ''
@secure()
param anthropicApiKey string = ''
@secure()
param webSearchApiKey string = ''

var secretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var secretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

resource ghSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(githubToken)) {
  parent: kv
  name: 'github-token'
  properties: {
    value: githubToken
  }
}

resource anthropicSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(anthropicApiKey)) {
  parent: kv
  name: 'anthropic-api-key'
  properties: {
    value: anthropicApiKey
  }
}

resource searchSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(webSearchApiKey)) {
  parent: kv
  name: 'web-search-api-key'
  properties: {
    value: webSearchApiKey
  }
}

resource agentSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, agentPrincipalId, secretsUser)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUser)
    principalId: agentPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  name: guid(kv.id, deployerPrincipalId, secretsOfficer)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsOfficer)
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

output name string = kv.name
output uri string = kv.properties.vaultUri
// Names of the secrets that actually exist, so the job references only those.
// Only names are output, never values.
var configuredSecretNames = concat(
  empty(githubToken) ? [] : ['github-token'],
  empty(anthropicApiKey) ? [] : ['anthropic-api-key'],
  empty(webSearchApiKey) ? [] : ['web-search-api-key']
)
#disable-next-line outputs-should-not-contain-secrets
output secretNames array = configuredSecretNames

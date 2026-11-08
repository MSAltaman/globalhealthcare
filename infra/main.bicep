// ============================================================================
// Global Healthcare Atlas — infrastructure
// ----------------------------------------------------------------------------
// Deploys everything the research agent needs, at subscription scope:
//
//   Resource group
//   ├── User-assigned managed identity   (the agent's only identity; no keys)
//   ├── Log Analytics + App Insights     (daily ingestion cap keeps it free-tier)
//   ├── Storage account                  (source cache, extracted claims, site data)
//   ├── Key Vault                        (GitHub token + optional API keys)
//   ├── Microsoft Foundry account/project + Claude deployments (Entra ID only)
//   ├── Container Apps environment + scheduled Job (the agent; scales to zero)
//   ├── Static Web App                   (the public site; built by GitHub Actions)
//   ├── Azure Container Registry         (optional; off by default — use GHCR)
//   └── Monthly cost budget with email alerts
//
// Pick a cost tier with one of the parameter files in ./params.
// ============================================================================
targetScope = 'subscription'

// ---------------------------------------------------------------- general --
@description('Short environment name, e.g. "prod" or "dev". Used in resource names.')
@maxLength(8)
param environmentName string = 'prod'

@description('Base name for resources.')
@maxLength(10)
param baseName string = 'hcatlas'

@description('Region. eastus2 hosts every Claude family in Foundry and supports Static Web Apps.')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string = 'eastus2'

@description('Static Web Apps is only offered in a few regions; eastus2 is one of them.')
@allowed([
  'eastus2'
  'centralus'
  'westus2'
  'westeurope'
  'eastasia'
])
param staticWebAppLocation string = 'eastus2'

@description('Cost tier label written to tags and passed to the agent.')
@allowed([
  'lean'
  'balanced'
  'deep'
])
param costTier string = 'lean'

@description('Object ID of the person deploying (az ad signed-in-user show --query id -o tsv). Grants you Key Vault secret management and model access for local testing. Leave empty to skip.')
param deployerPrincipalId string = ''

// --------------------------------------------------------------- LLM side --
@description('Where the agent calls Claude. "foundry" = Microsoft Foundry (Entra ID). "anthropic" = Anthropic API key stored in Key Vault (fallback if your subscription is not eligible for Claude in Foundry).')
@allowed([
  'foundry'
  'anthropic'
])
param llmBackend string = 'foundry'

@description('Claude model IDs per family. Empty string = do not deploy that family. Verify the IDs your region offers before deploying (see README).')
param haikuModel string = 'claude-haiku-5-5'
param sonnetModel string = ''
param opusModel string = ''

@description('Capacity per family in thousands of tokens per minute. This is a rate limit, not a reservation — you pay only for tokens used.')
param haikuCapacity int = 25
param sonnetCapacity int = 25
param opusCapacity int = 25

@description('Foundry hosting version: "2" = hosted on Azure (default in Foundry; data stays in Azure), "1" = hosted on Anthropic infrastructure.')
@allowed([
  '1'
  '2'
])
param modelVersion string = '2'

@description('Attestation sent to Anthropic with each Foundry deployment (accepts the Anthropic Marketplace terms). Must match your real legal entity.')
param claudeOrganizationName string = ''
@minLength(2)
@maxLength(2)
param claudeCountryCode string = 'US'
@allowed([
  'technology'
  'finance'
  'healthcare'
  'education'
  'retail'
  'manufacturing'
  'government'
  'media'
  'other'
])
param claudeIndustry string = 'technology'

@description('Which family the agent uses for each pipeline stage: screening/extraction, verification, and narrative synthesis.')
@allowed([
  'haiku'
  'sonnet'
  'opus'
])
param extractModelFamily string = 'haiku'
@allowed([
  'haiku'
  'sonnet'
  'opus'
])
param verifyModelFamily string = 'haiku'
@allowed([
  'haiku'
  'sonnet'
  'opus'
])
param synthModelFamily string = 'haiku'

// ---------------------------------------------------------------- the job --
@description('Container image for the agent. The default is a Microsoft placeholder so the infrastructure deploys before the agent code exists.')
param agentImage string = 'mcr.microsoft.com/k8se/quickstart-jobs:latest'

@description('UTC cron schedule for the full refresh run.')
param scheduleCron string = '0 6 1 1,4,7,10 *'

@description('Countries processed per run. Lower = cheaper runs; the agent resumes where it left off.')
@minValue(1)
@maxValue(200)
param countriesPerRun int = 10

@description('vCPU and memory for each run. 0.5 vCPU / 1Gi stays inside the Container Apps monthly free grant for typical runs.')
param jobCpu string = '0.5'
param jobMemory string = '1Gi'

@description('Max minutes a single run may take before it is stopped.')
@minValue(10)
@maxValue(1440)
param jobTimeoutMinutes int = 240

@description('GitHub repo the agent opens pull requests against, as owner/name. Can be set later.')
param githubRepo string = ''
param githubBranch string = 'main'

@description('Contact email sent to free scholarly APIs (OpenAlex, NCBI/PubMed, Crossref) as they request. Optional but recommended.')
param apiContactEmail string = ''

@description('Optional secrets. Leave empty now and add later; the job only references the ones you provide.')
@secure()
param githubToken string = ''
@secure()
param anthropicApiKey string = ''
@secure()
param webSearchApiKey string = ''

@description('Deploy an Azure Container Registry (Basic, small monthly fee). False = pull the agent image from GitHub Container Registry or another public registry.')
param deployContainerRegistry bool = false

// ----------------------------------------------------------- site + costs --
@description('Static Web Apps plan. Free includes 2 custom domains and free SSL; Standard adds SLA, more domains and private endpoints.')
@allowed([
  'Free'
  'Standard'
])
param staticWebAppSku string = 'Free'

@description('Log Analytics daily ingestion cap in GB. 0.1 keeps you well inside the monthly free allowance.')
param logDailyCapGb string = '0.1'

@description('Monthly budget in USD for the resource group. Alerts at 50/80/100% actual and 100% forecast.')
param monthlyBudgetUsd int = 25

@description('Email(s) that receive budget alerts.')
param budgetAlertEmails array = []

@description('First day of the current month, required by the budget API. Leave the default.')
param budgetStartDate string = utcNow('yyyy-MM-01')

// =============================================================================
var suffix = take(uniqueString(subscription().id, baseName, environmentName), 6)
var namePrefix = '${baseName}-${environmentName}'
var tags = {
  project: 'global-healthcare-atlas'
  environment: environmentName
  costTier: costTier
  managedBy: 'bicep'
}

var deployFoundry = llmBackend == 'foundry'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${namePrefix}'
  location: location
  tags: tags
}

module identity 'modules/identity.bicep' = {
  scope: rg
  params: {
    name: 'id-${namePrefix}-agent'
    location: location
    tags: tags
  }
}

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    dailyCapGb: logDailyCapGb
  }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  params: {
    name: take(toLower(replace('st${baseName}${environmentName}${suffix}', '-', '')), 24)
    location: location
    tags: tags
    agentPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
  }
}

module keyVault 'modules/keyvault.bicep' = {
  scope: rg
  params: {
    name: take('kv-${baseName}-${environmentName}-${suffix}', 24)
    location: location
    tags: tags
    agentPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
    githubToken: githubToken
    anthropicApiKey: anthropicApiKey
    webSearchApiKey: webSearchApiKey
  }
}

module foundry 'modules/foundry.bicep' = if (deployFoundry) {
  scope: rg
  params: {
    accountName: 'aif-${namePrefix}-${suffix}'
    projectName: 'proj-${namePrefix}'
    location: location
    tags: tags
    haikuModel: haikuModel
    sonnetModel: sonnetModel
    opusModel: opusModel
    haikuCapacity: haikuCapacity
    sonnetCapacity: sonnetCapacity
    opusCapacity: opusCapacity
    modelVersion: modelVersion
    claudeOrganizationName: claudeOrganizationName
    claudeCountryCode: claudeCountryCode
    claudeIndustry: claudeIndustry
    agentPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
  }
}

module registry 'modules/registry.bicep' = if (deployContainerRegistry) {
  scope: rg
  params: {
    name: take(toLower(replace('acr${baseName}${environmentName}${suffix}', '-', '')), 50)
    location: location
    tags: tags
    agentPrincipalId: identity.outputs.principalId
  }
}

// Model names the agent passes as `model` on each call. On Foundry this is the
// deployment name; on the Anthropic API it is the model ID itself.
var familyModels = {
  haiku: deployFoundry ? foundry!.outputs.haikuDeploymentName : haikuModel
  sonnet: deployFoundry ? foundry!.outputs.sonnetDeploymentName : sonnetModel
  opus: deployFoundry ? foundry!.outputs.opusDeploymentName : opusModel
}

module agentJob 'modules/containerapps-job.bicep' = {
  scope: rg
  params: {
    namePrefix: namePrefix
    location: location
    tags: tags
    identityId: identity.outputs.id
    identityClientId: identity.outputs.clientId
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsName
    image: agentImage
    registryServer: deployContainerRegistry ? registry!.outputs.loginServer : ''
    scheduleCron: scheduleCron
    cpu: jobCpu
    memory: jobMemory
    timeoutSeconds: jobTimeoutMinutes * 60
    keyVaultUri: keyVault.outputs.uri
    secretNames: keyVault.outputs.secretNames
    env: [
      { name: 'COST_TIER', value: costTier }
      { name: 'LLM_BACKEND', value: llmBackend }
      { name: 'ANTHROPIC_BASE_URL', value: deployFoundry ? foundry!.outputs.claudeBaseUrl : 'https://api.anthropic.com' }
      { name: 'MODEL_EXTRACT', value: familyModels[extractModelFamily] }
      { name: 'MODEL_VERIFY', value: familyModels[verifyModelFamily] }
      { name: 'MODEL_SYNTH', value: familyModels[synthModelFamily] }
      { name: 'COUNTRIES_PER_RUN', value: string(countriesPerRun) }
      { name: 'STORAGE_ACCOUNT_URL', value: storage.outputs.blobEndpoint }
      { name: 'CONTAINER_SOURCES', value: 'sources' }
      { name: 'CONTAINER_CLAIMS', value: 'claims' }
      { name: 'CONTAINER_SITE_DATA', value: 'site-data' }
      { name: 'CONTAINER_RUNS', value: 'runs' }
      { name: 'KEY_VAULT_URI', value: keyVault.outputs.uri }
      { name: 'GITHUB_REPO', value: githubRepo }
      { name: 'GITHUB_BRANCH', value: githubBranch }
      { name: 'API_CONTACT_EMAIL', value: apiContactEmail }
      { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: monitoring.outputs.appInsightsConnectionString }
    ]
  }
}

module site 'modules/staticwebapp.bicep' = {
  scope: rg
  params: {
    name: 'swa-${namePrefix}'
    location: staticWebAppLocation
    tags: tags
    sku: staticWebAppSku
  }
}

module budget 'modules/budget.bicep' = if (!empty(budgetAlertEmails)) {
  scope: rg
  params: {
    name: 'budget-${namePrefix}'
    amount: monthlyBudgetUsd
    startDate: budgetStartDate
    contactEmails: budgetAlertEmails
  }
}

// ----------------------------------------------------------------- outputs --
output resourceGroupName string = rg.name
output agentIdentityClientId string = identity.outputs.clientId
output storageAccountName string = storage.outputs.name
output keyVaultName string = keyVault.outputs.name
output jobName string = agentJob.outputs.jobName
output staticWebAppName string = site.outputs.name
output staticWebAppUrl string = 'https://${site.outputs.defaultHostname}'
output claudeBaseUrl string = deployFoundry ? foundry!.outputs.claudeBaseUrl : 'https://api.anthropic.com'
output modelExtract string = familyModels[extractModelFamily]
output modelVerify string = familyModels[verifyModelFamily]
output modelSynth string = familyModels[synthModelFamily]
output registryLoginServer string = deployContainerRegistry ? registry!.outputs.loginServer : ''

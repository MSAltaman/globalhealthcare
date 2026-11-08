// Phase 1 infrastructure: just the public site. The research agent runs as a
// Claude scheduled task, so no compute, storage or models are needed in Azure.
// Deploy into an existing resource group:
//   az group create -n rg-hcatlas-prod -l eastus2
//   az deployment group create -g rg-hcatlas-prod -f infra/site-only/main.bicep \
//     -p budgetAlertEmails='["you@example.com"]'
targetScope = 'resourceGroup'

@description('Static Web Apps regions: eastus2, centralus, westus2, westeurope, eastasia.')
@allowed([
  'eastus2'
  'centralus'
  'westus2'
  'westeurope'
  'eastasia'
])
param location string = 'eastus2'

param name string = 'swa-hcatlas-prod'

@allowed([
  'Free'
  'Standard'
])
param sku string = 'Free'

@description('Optional budget alert emails. Empty = no budget.')
param budgetAlertEmails array = []
param monthlyBudgetUsd int = 5
param budgetStartDate string = utcNow('yyyy-MM-01')

var tags = {
  project: 'global-healthcare-atlas'
  phase: 'site-only'
  managedBy: 'bicep'
}

module site '../modules/staticwebapp.bicep' = {
  params: {
    name: name
    location: location
    tags: tags
    sku: sku
  }
}

module budget '../modules/budget.bicep' = if (!empty(budgetAlertEmails)) {
  params: {
    name: 'budget-hcatlas-site'
    amount: monthlyBudgetUsd
    startDate: budgetStartDate
    contactEmails: budgetAlertEmails
  }
}

output staticWebAppName string = site.outputs.name
output url string = 'https://${site.outputs.defaultHostname}'

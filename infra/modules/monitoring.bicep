// Log Analytics + workspace-based Application Insights with a hard daily cap.
param namePrefix string
param location string
param tags object

@description('Daily ingestion cap in GB (string so fractional values like 0.1 work).')
param dailyCapGb string

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${namePrefix}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: json(dailyCapGb)
    }
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${namePrefix}'
  location: location
  tags: tags
  kind: 'other'
  properties: {
    Application_Type: 'other'
    WorkspaceResourceId: law.id
    IngestionMode: 'LogAnalytics'
  }
}

output logAnalyticsName string = law.name
output logAnalyticsCustomerId string = law.properties.customerId
output appInsightsConnectionString string = appi.properties.ConnectionString

// Consumption-only Container Apps environment and the scheduled agent job.
// Nothing runs (or bills) between runs; typical runs fit inside the monthly
// Container Apps free grant.
param namePrefix string
param location string
param tags object

param identityId string
param identityClientId string

param logAnalyticsCustomerId string
param logAnalyticsWorkspaceName string

param image string
@description('Private registry login server, or empty for a public image.')
param registryServer string = ''

param scheduleCron string
param cpu string
param memory string
param timeoutSeconds int

param keyVaultUri string
@description('Key Vault secret names to expose to the job as environment variables.')
param secretNames array

@description('Plain environment variables: [{ name, value }].')
param env array

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${namePrefix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// Secret "github-token" becomes env var GITHUB_TOKEN, and so on.
var secretRefs = [
  for s in secretNames: {
    name: s
    keyVaultUrl: '${keyVaultUri}secrets/${s}'
    identity: identityId
  }
]
var secretEnv = [
  for s in secretNames: {
    name: toUpper(replace(s, '-', '_'))
    secretRef: s
  }
]

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: 'job-${namePrefix}-agent'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: scheduleCron
        parallelism: 1
        replicaCompletionCount: 1
      }
      replicaTimeout: timeoutSeconds
      // Retry once; a second failure needs a human to look at the run log.
      replicaRetryLimit: 1
      secrets: secretRefs
      registries: empty(registryServer)
        ? []
        : [
            {
              server: registryServer
              identity: identityId
            }
          ]
    }
    template: {
      containers: [
        {
          name: 'agent'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat(env, secretEnv, [
            {
              // Tells DefaultAzureCredential which identity to use.
              name: 'AZURE_CLIENT_ID'
              value: identityClientId
            }
          ])
        }
      ]
    }
  }
}

output jobName string = job.name
output environmentName string = cae.name

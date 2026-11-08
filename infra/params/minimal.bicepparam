// MINIMAL — lowest possible cost. Haiku for every stage; accuracy comes from
// code checking every quoted passage against the cached source, plus a Sonnet
// spot-check on a sample of claims. Refresh twice a year, changed sources only.
// Expect about $1–3/month, and roughly $0.15–0.25 per country to build.
using '../main.bicep'

param environmentName = 'prod'
param costTier = 'lean'
param location = 'eastus2'

// --- Fill these in -----------------------------------------------------------
param claudeOrganizationName = '' // your legal entity name, exactly as registered
param budgetAlertEmails = [] // e.g. ['you@yourdomain.com']
param deployerPrincipalId = '' // az ad signed-in-user show --query id -o tsv
param apiContactEmail = '' // sent to OpenAlex / PubMed / Crossref as they request
param githubRepo = 'MSAltaman/globalheathcare'
// -----------------------------------------------------------------------------

param llmBackend = 'foundry'
param haikuModel = 'claude-haiku-5-5'
// Sonnet is used only for the small QA spot-check sample.
param sonnetModel = 'claude-sonnet-5-5'
param opusModel = ''
param haikuCapacity = 50
param sonnetCapacity = 10

param extractModelFamily = 'haiku'
param verifyModelFamily = 'haiku'
param synthModelFamily = 'haiku'

// 06:00 UTC on Jan 1 and Jul 1
param scheduleCron = '0 6 1 1,7 *'
param countriesPerRun = 5
param jobTimeoutMinutes = 120

param staticWebAppSku = 'Free'
param deployContainerRegistry = false
param logDailyCapGb = '0.05'
param monthlyBudgetUsd = 10

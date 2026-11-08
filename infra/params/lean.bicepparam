// LEAN — lowest cost. Haiku does screening, extraction and writing; Sonnet does
// the fact-check step (the one place model quality matters most for accuracy).
// Quarterly refresh. Expect roughly $3–8/month after the initial build.
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
param sonnetModel = 'claude-sonnet-5-5'
param opusModel = ''
param haikuCapacity = 50
param sonnetCapacity = 25

param extractModelFamily = 'haiku'
param verifyModelFamily = 'sonnet'
param synthModelFamily = 'haiku'

// 06:00 UTC on the 1st of Jan/Apr/Jul/Oct
param scheduleCron = '0 6 1 1,4,7,10 *'
param countriesPerRun = 15
param jobTimeoutMinutes = 240

param staticWebAppSku = 'Free'
param deployContainerRegistry = false
param logDailyCapGb = '0.1'
param monthlyBudgetUsd = 25

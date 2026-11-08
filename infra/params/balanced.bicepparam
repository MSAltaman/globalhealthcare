// BALANCED — recommended. Sonnet extracts claims from sources and writes the
// profiles; Haiku screens search results; Sonnet fact-checks.
// Monthly refresh. Expect roughly $15–30/month after the initial build.
using '../main.bicep'

param environmentName = 'prod'
param costTier = 'balanced'
param location = 'eastus2'

// --- Fill these in -----------------------------------------------------------
param claudeOrganizationName = ''
param budgetAlertEmails = []
param deployerPrincipalId = ''
param apiContactEmail = ''
param githubRepo = 'MSAltaman/globalhealthcare'
// -----------------------------------------------------------------------------

param llmBackend = 'foundry'
param haikuModel = 'claude-haiku-5-5'
param sonnetModel = 'claude-sonnet-5-5'
param opusModel = ''
param haikuCapacity = 50
param sonnetCapacity = 50

param extractModelFamily = 'sonnet'
param verifyModelFamily = 'sonnet'
param synthModelFamily = 'sonnet'

// 06:00 UTC on the 1st of every month
param scheduleCron = '0 6 1 * *'
param countriesPerRun = 20
param jobTimeoutMinutes = 360

param staticWebAppSku = 'Free'
param deployContainerRegistry = false
param logDailyCapGb = '0.2'
param monthlyBudgetUsd = 60

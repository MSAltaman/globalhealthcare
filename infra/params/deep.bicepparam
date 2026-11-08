// DEEP — highest quality. Sonnet extracts; Opus fact-checks and writes, so the
// checker is a different, stronger model than the extractor.
// Weekly check for changed sources. Expect roughly $40–70/month after the initial build.
using '../main.bicep'

param environmentName = 'prod'
param costTier = 'deep'
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
param opusModel = 'claude-opus-5-5'
param haikuCapacity = 50
param sonnetCapacity = 50
param opusCapacity = 50

param extractModelFamily = 'sonnet'
param verifyModelFamily = 'opus'
param synthModelFamily = 'opus'

// 06:00 UTC every Sunday
param scheduleCron = '0 6 * * 0'
param countriesPerRun = 25
param jobTimeoutMinutes = 480
param jobCpu = '1.0'
param jobMemory = '2Gi'

param staticWebAppSku = 'Free'
param deployContainerRegistry = false
param logDailyCapGb = '0.3'
param monthlyBudgetUsd = 125

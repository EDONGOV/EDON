@description('Azure region')
param location string = resourceGroup().location

@description('Container image for EDON Gateway')
param gatewayImage string

@description('Container app environment name')
param environmentName string = 'edon-hipaa-env'

@description('Gateway app name')
param appName string = 'edon-gateway'

@description('Existing Key Vault name that stores EDON secrets')
param keyVaultName string

@description('Existing Log Analytics workspace customer id')
param logAnalyticsCustomerId string

@secure()
@description('Existing Log Analytics shared key')
param logAnalyticsSharedKey string

resource managedEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

resource gateway 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnv.id
    configuration: {
      ingress: {
        external: false
        targetPort: 8000
        transport: 'http'
      }
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: 'https://${keyVaultName}.vault.azure.net/secrets/DATABASE-URL'
          identity: 'system'
        }
        {
          name: 'edon-api-token'
          keyVaultUrl: 'https://${keyVaultName}.vault.azure.net/secrets/EDON-API-TOKEN'
          identity: 'system'
        }
        {
          name: 'edon-db-encryption-key'
          keyVaultUrl: 'https://${keyVaultName}.vault.azure.net/secrets/EDON-DB-ENCRYPTION-KEY'
          identity: 'system'
        }
        {
          name: 'edon-signing-key-hex'
          keyVaultUrl: 'https://${keyVaultName}.vault.azure.net/secrets/EDON-SIGNING-KEY-HEX'
          identity: 'system'
        }
        {
          name: 'edon-audit-chain-signing-key'
          keyVaultUrl: 'https://${keyVaultName}.vault.azure.net/secrets/EDON-AUDIT-CHAIN-SIGNING-KEY'
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'gateway'
          image: gatewayImage
          env: [
            { name: 'EDON_ENV', value: 'production' }
            { name: 'ENVIRONMENT', value: 'production' }
            { name: 'EDON_CLOUD_PROVIDER', value: 'azure' }
            { name: 'EDON_HIPAA_DEPLOYMENT_PROFILE', value: 'true' }
            { name: 'EDON_PRIVATE_NETWORK_ENABLED', value: 'true' }
            { name: 'EDON_WAF_ENABLED', value: 'true' }
            { name: 'EDON_MANAGED_POSTGRES', value: 'true' }
            { name: 'EDON_ENTERPRISE_MODE', value: 'true' }
            { name: 'EDON_ENTERPRISE_SSO_ONLY', value: 'true' }
            { name: 'EDON_AUTH_ENABLED', value: 'true' }
            { name: 'EDON_CREDENTIALS_STRICT', value: 'true' }
            { name: 'EDON_TOKEN_BINDING_ENABLED', value: 'true' }
            { name: 'EDON_ENCRYPT_AUDIT_PAYLOAD', value: 'true' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'EDON_API_TOKEN', secretRef: 'edon-api-token' }
            { name: 'EDON_DB_ENCRYPTION_KEY', secretRef: 'edon-db-encryption-key' }
            { name: 'EDON_SIGNING_KEY_HEX', secretRef: 'edon-signing-key-hex' }
            { name: 'EDON_AUDIT_CHAIN_SIGNING_KEY', secretRef: 'edon-audit-chain-signing-key' }
            { name: 'AZURE_KEY_VAULT_URL', value: 'https://${keyVaultName}.vault.azure.net/' }
          ]
        }
      ]
      scale: {
        minReplicas: 2
        maxReplicas: 10
      }
    }
  }
}

output gatewayPrincipalId string = gateway.identity.principalId

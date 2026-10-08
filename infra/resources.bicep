targetScope = 'resourceGroup'

param registryName string
param location string
param containerImage string

resource acr 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: 'finance-dashboard-env'
  location: location
  properties: {
    vnetConfiguration: {}
  }
}

resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'finance-dashboard-app'
  location: location
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, appIdentity.id, 'AcrPull')
  scope: acr
  properties: {
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: 'financedashboarddata'
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2025-06-01' = {
  name: 'default'
  parent: storageAccount
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2025-06-01' = {
  name: 'finance-data'
  parent: fileService
  properties: {
    accessTier: 'Cool'
    enabledProtocols: 'SMB'
    shareQuota: 1
  }
}

resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2026-01-01' = {
  name: 'finance-data'
  parent: containerAppsEnvironment
  properties: {
    azureFile: {
      accessMode: 'ReadWrite'
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: fileShare.name
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2025-07-01' = {
  name: 'finance-dashboard'
  location: location

  dependsOn: [
    environmentStorage
  ]

  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${appIdentity.id}': {}
    }
  }

  properties: {
    managedEnvironmentId: containerAppsEnvironment.id

    configuration: {
      ingress: {
        external: true
        targetPort: 8501
        transport: 'auto'
      }

      registries: [
        {
          server: '${registryName}.azurecr.io'
          identity: appIdentity.id
        }
      ]
    }

    template: {
      containers: [
        {
          name: 'finance-dashboard'
          image: containerImage

          resources: {
            cpu: any('0.5')
            memory: '1Gi'
          }

          volumeMounts: [
            {
              volumeName: 'finance-data-volume'
              mountPath: '/data'
            }
          ]
        }
      ]

      volumes: [
        {
          name: 'finance-data-volume'
          storageType: 'AzureFile'
          storageName: 'finance-data'
        }
      ]

      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

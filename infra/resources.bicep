targetScope = 'resourceGroup'

param registryName string
param location string

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

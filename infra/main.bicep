targetScope = 'subscription'

param location string = 'uksouth'
param resourceGroupName string = 'finance-dashboard-rg'
param registryName string = 'financedashboardacr'
param containerImage string

resource rg 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
}

module resources './resources.bicep' = {
  name: 'financeDashboardResources'
  scope: rg
  params: {
    registryName: registryName
    location: location
    containerImage: containerImage

  }
}


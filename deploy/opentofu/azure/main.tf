provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = var.tags
}

# 1. Key Vault & Credentials Management
module "key_vault" {
  source              = "./modules/key_vault"
  name_prefix         = var.name_prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = var.tags
}

# 2. Virtual Network & Subnets
module "vnet" {
  source              = "./modules/vnet"
  name_prefix         = var.name_prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = var.tags
}

# 3. Azure Monitor & Log Analytics Workspace
module "monitoring" {
  source               = "./modules/monitoring"
  name_prefix          = var.name_prefix
  resource_group_name  = azurerm_resource_group.main.name
  location             = var.location
  postgresql_server_id = module.postgresql.server_id
  tags                 = var.tags
}

# 4. Managed AKS Cluster
module "aks" {
  source                     = "./modules/aks"
  cluster_name               = "${var.name_prefix}-aks"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = var.location
  subnet_id                  = module.vnet.aks_subnet_id
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
  tags                       = var.tags
}

# 5. PostgreSQL Flexible Server
module "postgresql" {
  source              = "./modules/postgresql"
  name_prefix         = var.name_prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  vnet_id             = module.vnet.vnet_id
  delegated_subnet_id = module.vnet.postgres_subnet_id
  admin_password      = module.key_vault.database_password
  tags                = var.tags
}

# 6. Object Storage (Azure Blob CAS Artifacts)
module "blob" {
  source              = "./modules/blob"
  name_prefix         = var.name_prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = var.tags
}

# 7. GPU Node Pool
module "gpu" {
  source     = "./modules/gpu"
  cluster_id = module.aks.cluster_id
  subnet_id  = module.vnet.aks_subnet_id
  tags       = var.tags
}

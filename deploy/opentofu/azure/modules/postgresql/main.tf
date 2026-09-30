# Private DNS Zone for PostgreSQL Flexible Server
resource "azurerm_private_dns_zone" "postgres" {
  name                = "${var.name_prefix}.postgres.database.azure.com"
  resource_group_name = var.resource_group_name

  tags = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "${var.name_prefix}-pg-dns-link"
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = var.vnet_id
  resource_group_name   = var.resource_group_name
}

# Zone-Redundant PostgreSQL Flexible Server (PostgreSQL 16)
resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "${var.name_prefix}-psql"
  resource_group_name    = var.resource_group_name
  location               = var.location
  version                = "16"
  delegated_subnet_id    = var.delegated_subnet_id
  private_dns_zone_id    = azurerm_private_dns_zone.postgres.id
  administrator_login    = var.admin_username
  administrator_password = var.admin_password
  zone                   = "1"

  storage_mb   = var.storage_mb
  storage_tier = "P10"
  sku_name     = var.sku_name

  backup_retention_days        = 14
  geo_redundant_backup_enabled = false
  auto_grow_enabled            = true

  high_availability {
    mode                      = "ZoneRedundant"
    standby_availability_zone = "2"
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]

  tags = var.tags
}

# Production Database
resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "agentspace"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

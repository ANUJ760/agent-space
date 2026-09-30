resource "random_string" "storage_suffix" {
  length  = 6
  special = false
  upper   = false
}

# Azure Storage Account for Content Addressable Storage (CAS)
resource "azurerm_storage_account" "artifacts" {
  name                     = "${lower(replace(var.name_prefix, "-", ""))}cas${random_string.storage_suffix.result}"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "ZRS" # Zone-redundant storage

  enable_https_traffic_only       = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 30
    }
  }

  tags = var.tags
}

# CAS Artifacts Blob Container
resource "azurerm_storage_container" "artifacts" {
  name                  = "agentspace-artifacts"
  storage_account_name  = azurerm_storage_account.artifacts.name
  container_access_type = "private"
}

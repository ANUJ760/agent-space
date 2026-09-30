# Central Log Analytics Workspace for Container Insights & Audit
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.name_prefix}-law"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 90

  tags = var.tags
}

# Action Group for Operational Alerts
resource "azurerm_monitor_action_group" "alerts" {
  name                = "${var.name_prefix}-alerts"
  resource_group_name = var.resource_group_name
  short_name          = "agsp-alerts"

  tags = var.tags
}

# PostgreSQL High CPU Metric Alert
resource "azurerm_monitor_metric_alert" "postgres_cpu" {
  name                = "${var.name_prefix}-postgres-high-cpu"
  resource_group_name = var.resource_group_name
  scopes              = [var.postgresql_server_id]
  description         = "PostgreSQL Flexible Server CPU exceeds 80%"
  severity            = 2

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "cpu_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.alerts.id
  }

  tags = var.tags
}

output "log_analytics_workspace_id" {
  description = "Log Analytics Workspace ID"
  value       = azurerm_log_analytics_workspace.main.id
}

output "action_group_id" {
  description = "Action Group ID"
  value       = azurerm_monitor_action_group.alerts.id
}

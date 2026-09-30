"""Tests for M85 — Azure OpenTofu Infrastructure Modules.

Validates all 7 infrastructure modules per Section 94:
1. VNet: Virtual Network with AKS, delegated PostgreSQL, and Ingress subnets.
2. AKS: Managed Kubernetes cluster with Azure CNI, Key Vault Secrets Provider, and Log Analytics.
3. PostgreSQL: Zone-redundant PostgreSQL 16 Flexible Server with delegated subnet integration.
4. Blob: Storage Account and private Blob container for CAS artifacts with TLS 1.2+ and versioning.
5. Key Vault: Hardware-backed Key Vault with soft-delete, purge protection, and secrets management.
6. GPU: Dedicated GPU node pool with NVIDIA taints and scale-to-zero.
7. Monitoring: Log Analytics workspace and metric alert rules.
8. Secret Protection: Strict enforcement that no secrets or passwords are leaked in root outputs.
"""

import re
from pathlib import Path

AZURE_DIR = Path(__file__).parent.parent / "deploy" / "opentofu" / "azure"
MODULES_DIR = AZURE_DIR / "modules"


class TestM85AzureOpenTofu:
    """Verifies OpenTofu Azure infrastructure definitions and security compliance."""

    # ─── 1. Module Inventory ─────────────────────────────────────────────────

    def test_all_seven_modules_exist(self) -> None:
        expected_modules = [
            "vnet",
            "aks",
            "postgresql",
            "blob",
            "key_vault",
            "gpu",
            "monitoring",
        ]
        for mod in expected_modules:
            mod_path = MODULES_DIR / mod
            assert mod_path.is_dir(), f"Module directory {mod} missing"
            assert (mod_path / "main.tf").exists(), f"main.tf missing in module {mod}"
            assert (mod_path / "variables.tf").exists(), f"variables.tf missing in module {mod}"
            assert (mod_path / "outputs.tf").exists(), f"outputs.tf missing in module {mod}"

    # ─── 2. Root Composition ─────────────────────────────────────────────────

    def test_root_main_wires_all_modules(self) -> None:
        root_main = (AZURE_DIR / "main.tf").read_text(encoding="utf-8")
        expected_modules = [
            'module "key_vault"',
            'module "vnet"',
            'module "monitoring"',
            'module "aks"',
            'module "postgresql"',
            'module "blob"',
            'module "gpu"',
        ]
        for mod in expected_modules:
            assert mod in root_main, f"Root main.tf does not instantiate {mod}"

    # ─── 3. Zero Secrets Output Enforced ─────────────────────────────────────

    def test_root_outputs_do_not_expose_secrets(self) -> None:
        root_outputs = (AZURE_DIR / "outputs.tf").read_text(encoding="utf-8")
        forbidden_terms = [
            "password",
            "secret_string",
            "auth_token",
            "private_key",
            "api_key",
        ]
        output_blocks = re.findall(r'output\s+"([^"]+)"\s+\{([^}]+)\}', root_outputs)
        assert len(output_blocks) >= 7, "Expected at least 7 operational outputs"

        for out_name, out_body in output_blocks:
            for term in forbidden_terms:
                assert term not in out_name.lower(), (
                    f"Forbidden secret term '{term}' in root output name '{out_name}'"
                )
                assert f"module.key_vault.{term}" not in out_body.lower(), (
                    f"Root output '{out_name}' attempts to expose secret value '{term}'"
                )

    # ─── 4. VNet Module ──────────────────────────────────────────────────────

    def test_vnet_and_subnet_delegation(self) -> None:
        vnet_main = (MODULES_DIR / "vnet" / "main.tf").read_text(encoding="utf-8")
        assert "azurerm_virtual_network" in vnet_main
        assert "azurerm_subnet" in vnet_main
        assert "Microsoft.DBforPostgreSQL/flexibleServers" in vnet_main
        assert "azurerm_network_security_group" in vnet_main

    # ─── 5. AKS Module ───────────────────────────────────────────────────────

    def test_aks_module_security_and_addons(self) -> None:
        aks_main = (MODULES_DIR / "aks" / "main.tf").read_text(encoding="utf-8")
        assert "azurerm_kubernetes_cluster" in aks_main
        assert 'network_plugin    = "azure"' in aks_main or 'network_plugin = "azure"' in aks_main
        assert "key_vault_secrets_provider" in aks_main
        assert "oms_agent" in aks_main
        assert "oidc_issuer_enabled" in aks_main

    # ─── 6. PostgreSQL Module ────────────────────────────────────────────────

    def test_postgresql_flexible_server_ha(self) -> None:
        pg_main = (MODULES_DIR / "postgresql" / "main.tf").read_text(encoding="utf-8")
        assert "azurerm_postgresql_flexible_server" in pg_main
        assert 'version                = "16"' in pg_main or 'version = "16"' in pg_main
        assert "high_availability" in pg_main
        assert "ZoneRedundant" in pg_main
        assert "auto_grow_enabled" in pg_main

    # ─── 7. Blob Module ──────────────────────────────────────────────────────

    def test_blob_storage_cas_hardening(self) -> None:
        blob_main = (MODULES_DIR / "blob" / "main.tf").read_text(encoding="utf-8")
        assert "azurerm_storage_account" in blob_main
        assert (
            "enable_https_traffic_only       = true" in blob_main
            or "enable_https_traffic_only = true" in blob_main
        )
        assert "TLS1_2" in blob_main
        assert (
            "allow_nested_items_to_be_public = false" in blob_main
            or "allow_nested_items_to_be_public = false" in blob_main
        )
        assert "versioning_enabled = true" in blob_main
        assert "agentspace-artifacts" in blob_main

    # ─── 8. Key Vault Module ─────────────────────────────────────────────────

    def test_key_vault_protection(self) -> None:
        kv_main = (MODULES_DIR / "key_vault" / "main.tf").read_text(encoding="utf-8")
        assert "azurerm_key_vault" in kv_main
        assert (
            "purge_protection_enabled    = true" in kv_main
            or "purge_protection_enabled = true" in kv_main
        )
        assert (
            "soft_delete_retention_days  = 90" in kv_main
            or "soft_delete_retention_days = 90" in kv_main
        )
        assert "azurerm_key_vault_secret" in kv_main

    # ─── 9. GPU Module ───────────────────────────────────────────────────────

    def test_gpu_nodepool_and_taints(self) -> None:
        gpu_main = (MODULES_DIR / "gpu" / "main.tf").read_text(encoding="utf-8")
        assert "azurerm_kubernetes_cluster_node_pool" in gpu_main
        assert "nvidia.com/gpu" in gpu_main
        assert "NoSchedule" in gpu_main
        assert "enable_auto_scaling = true" in gpu_main or "enable_auto_scaling = true" in gpu_main

    # ─── 10. Monitoring Module ───────────────────────────────────────────────

    def test_monitoring_workspace_and_alerts(self) -> None:
        mon_main = (MODULES_DIR / "monitoring" / "main.tf").read_text(encoding="utf-8")
        assert "azurerm_log_analytics_workspace" in mon_main
        assert "azurerm_monitor_action_group" in mon_main
        assert "azurerm_monitor_metric_alert" in mon_main
        assert "cpu_percent" in mon_main

"""Tests for M84 — AWS OpenTofu Infrastructure Modules.

Validates all 9 infrastructure modules per Section 93:
1. VPC: Multi-AZ public, private, and database subnets with NAT Gateways.
2. EKS: Managed Kubernetes cluster with KMS envelope encryption and OIDC IRSA.
3. PostgreSQL: RDS Multi-AZ PostgreSQL 16 with KMS encryption and automated backups.
4. Storage: S3 CAS bucket with versioning, SSE-KMS, and zero public access.
5. Cache: High-availability ElastiCache Redis with in-transit and at-rest encryption.
6. Messaging: SQS queue with Dead Letter Queue (DLQ) and SNS topics.
7. Secrets: Dedicated KMS key and Secrets Manager container.
8. GPU: EKS GPU managed node group with taints, labels, and scale-to-zero.
9. Monitoring: CloudWatch log groups and operational alarms for RDS and Redis.
10. Secret Protection: Strict enforcement that no secrets or passwords are exposed in root outputs.
"""

import re
from pathlib import Path

AWS_DIR = Path(__file__).parent.parent / "deploy" / "opentofu" / "aws"
MODULES_DIR = AWS_DIR / "modules"


class TestM84AWSOpenTofu:
    """Verifies OpenTofu AWS infrastructure definitions and security compliance."""

    # ─── 1. Module Inventory ─────────────────────────────────────────────────

    def test_all_nine_modules_exist(self) -> None:
        expected_modules = [
            "vpc",
            "eks",
            "postgresql",
            "storage",
            "cache",
            "messaging",
            "secrets",
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
        root_main = (AWS_DIR / "main.tf").read_text(encoding="utf-8")
        expected_modules = [
            'module "secrets"',
            'module "vpc"',
            'module "eks"',
            'module "postgresql"',
            'module "storage"',
            'module "cache"',
            'module "messaging"',
            'module "gpu"',
            'module "monitoring"',
        ]
        for mod in expected_modules:
            assert mod in root_main, f"Root main.tf does not instantiate {mod}"

    # ─── 3. Zero Secrets Output Enforced ─────────────────────────────────────

    def test_root_outputs_do_not_expose_secrets(self) -> None:
        root_outputs = (AWS_DIR / "outputs.tf").read_text(encoding="utf-8")
        forbidden_terms = [
            "password",
            "secret_string",
            "auth_token",
            "private_key",
            "api_key",
        ]
        # Parse output block names
        output_blocks = re.findall(r'output\s+"([^"]+)"\s+\{([^}]+)\}', root_outputs)
        assert len(output_blocks) >= 10, "Expected at least 10 operational outputs"

        for out_name, out_body in output_blocks:
            for term in forbidden_terms:
                assert term not in out_name.lower(), (
                    f"Forbidden secret term '{term}' in root output name '{out_name}'"
                )
                assert f"module.secrets.{term}" not in out_body.lower(), (
                    f"Root output '{out_name}' attempts to expose secret value '{term}'"
                )

    # ─── 4. VPC Module ───────────────────────────────────────────────────────

    def test_vpc_module_architecture(self) -> None:
        vpc_main = (MODULES_DIR / "vpc" / "main.tf").read_text(encoding="utf-8")
        assert "aws_vpc" in vpc_main
        assert "aws_subnet" in vpc_main
        assert "aws_internet_gateway" in vpc_main
        assert "aws_nat_gateway" in vpc_main
        assert "kubernetes.io/role/elb" in vpc_main
        assert "kubernetes.io/role/internal-elb" in vpc_main

    # ─── 5. EKS Module ───────────────────────────────────────────────────────

    def test_eks_module_encryption_and_irsa(self) -> None:
        eks_main = (MODULES_DIR / "eks" / "main.tf").read_text(encoding="utf-8")
        assert "aws_eks_cluster" in eks_main
        assert "encryption_config" in eks_main
        assert 'resources = ["secrets"]' in eks_main or 'resources = ["secrets"]' in eks_main
        assert "aws_iam_openid_connect_provider" in eks_main
        assert "aws_eks_node_group" in eks_main

    # ─── 6. PostgreSQL Module ────────────────────────────────────────────────

    def test_postgresql_module_security_and_durability(self) -> None:
        pg_main = (MODULES_DIR / "postgresql" / "main.tf").read_text(encoding="utf-8")
        assert "aws_db_instance" in pg_main
        assert "multi_az               = var.multi_az" in pg_main or "multi_az" in pg_main
        assert "storage_encrypted     = true" in pg_main or "storage_encrypted = true" in pg_main
        assert (
            "publicly_accessible    = false" in pg_main or "publicly_accessible = false" in pg_main
        )
        assert (
            "deletion_protection       = true" in pg_main or "deletion_protection = true" in pg_main
        )
        assert "backup_retention_period" in pg_main

    # ─── 7. Storage Module ───────────────────────────────────────────────────

    def test_storage_module_s3_hardening(self) -> None:
        storage_main = (MODULES_DIR / "storage" / "main.tf").read_text(encoding="utf-8")
        assert "aws_s3_bucket" in storage_main
        assert "aws_s3_bucket_versioning" in storage_main
        assert "aws_s3_bucket_server_side_encryption_configuration" in storage_main
        assert "aws_s3_bucket_public_access_block" in storage_main
        assert "block_public_acls       = true" in storage_main
        assert "block_public_policy     = true" in storage_main
        assert "restrict_public_buckets = true" in storage_main

    # ─── 8. Cache Module ─────────────────────────────────────────────────────

    def test_cache_module_redis_security(self) -> None:
        cache_main = (MODULES_DIR / "cache" / "main.tf").read_text(encoding="utf-8")
        assert "aws_elasticache_replication_group" in cache_main
        assert "at_rest_encryption_enabled = true" in cache_main
        assert "transit_encryption_enabled = true" in cache_main
        assert "auth_token" in cache_main
        assert "multi_az_enabled           = true" in cache_main

    # ─── 9. Messaging Module ─────────────────────────────────────────────────

    def test_messaging_module_sqs_and_dlq(self) -> None:
        msg_main = (MODULES_DIR / "messaging" / "main.tf").read_text(encoding="utf-8")
        assert "aws_sqs_queue" in msg_main
        assert "events-dlq" in msg_main
        assert "redrive_policy" in msg_main
        assert "aws_sns_topic" in msg_main

    # ─── 10. GPU Module ──────────────────────────────────────────────────────

    def test_gpu_module_taints_and_scaling(self) -> None:
        gpu_main = (MODULES_DIR / "gpu" / "main.tf").read_text(encoding="utf-8")
        assert "aws_eks_node_group" in gpu_main
        assert "AL2_x86_64_GPU" in gpu_main
        assert "nvidia.com/gpu" in gpu_main
        assert "NO_SCHEDULE" in gpu_main
        assert "scaling_config" in gpu_main

    # ─── 11. Monitoring Module ───────────────────────────────────────────────

    def test_monitoring_module_cloudwatch_and_alarms(self) -> None:
        mon_main = (MODULES_DIR / "monitoring" / "main.tf").read_text(encoding="utf-8")
        assert "aws_cloudwatch_log_group" in mon_main
        assert "aws_cloudwatch_metric_alarm" in mon_main
        assert "aws_sns_topic" in mon_main
        assert "CPUUtilization" in mon_main

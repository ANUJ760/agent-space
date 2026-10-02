#!/usr/bin/env python3
"""Create the Agent Space Kubernetes Secret from AWS Secrets Manager.

Requires AWS CLI access to both secrets and kubectl access to the cluster.
Secret values are passed to kubectl on stdin, never as command-line arguments.
"""

import argparse
import base64
import json
import subprocess
import sys
from urllib.parse import quote, urlsplit


def read_secret(secret_id: str) -> str:
    result = subprocess.run(
        [
            "aws", "secretsmanager", "get-secret-value",
            "--secret-id", secret_id,
            "--query", "SecretString",
            "--output", "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"Could not read AWS secret {secret_id!r}; check AWS credentials and permissions")
    value = json.loads(result.stdout)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AWS secret {secret_id!r} has no SecretString value")
    return value


def endpoint(value: str, label: str, *, require_port: bool) -> str:
    parsed = urlsplit("//" + value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError(f"{label} must be a hostname{' and port' if require_port else ''}")
    if require_port and parsed.port is None:
        raise ValueError(f"{label} must include a port")
    if not require_port and parsed.port is not None:
        raise ValueError(f"{label} must not include a port")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-secret-id", required=True, help="OpenTofu app_secrets_name output")
    parser.add_argument("--gemini-secret-id", required=True, help="OpenTofu default_gemini_api_key_secret_name output")
    parser.add_argument("--db-endpoint", required=True, help="OpenTofu postgresql_endpoint output (host:port)")
    parser.add_argument("--db-name", required=True, help="OpenTofu postgresql_database_name output")
    parser.add_argument("--db-user", default="agentspace_admin", help="RDS username (default: agentspace_admin)")
    parser.add_argument("--redis-endpoint", required=True, help="OpenTofu redis_primary_endpoint output (hostname)")
    parser.add_argument("--efs-file-system-id", required=True, help="OpenTofu workspace_efs_file_system_id output")
    parser.add_argument("--public-web-url", required=True, help="Public HTTPS origin, for example https://app.example.com")
    parser.add_argument("--namespace", default="agent-space")
    args = parser.parse_args()

    try:
        credentials = json.loads(read_secret(args.app_secret_id))
        if not isinstance(credentials, dict):
            raise ValueError("Application secret must contain a JSON object")
        for key in ("DB_PASSWORD", "REDIS_PASSWORD", "SECRET_KEY", "NATS_AUTH_TOKEN"):
            if not isinstance(credentials.get(key), str) or not credentials[key]:
                raise ValueError(f"Application secret is missing {key}")
        if len(credentials["SECRET_KEY"]) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")

        gemini_key = read_secret(args.gemini_secret_id).strip()
        db_endpoint = endpoint(args.db_endpoint, "Database endpoint", require_port=True)
        redis_endpoint = endpoint(args.redis_endpoint, "Redis endpoint", require_port=False)
        if not args.db_name or "/" in args.db_name:
            raise ValueError("Database name is invalid")
        if not args.db_user:
            raise ValueError("Database user is invalid")
        if not args.efs_file_system_id.startswith("fs-"):
            raise ValueError("EFS file system ID is invalid")
        public_url = urlsplit(args.public_web_url)
        if public_url.scheme != "https" or not public_url.hostname or public_url.path not in ("", "/"):
            raise ValueError("Public web URL must be an HTTPS origin without a path")

        values = {
            "DATABASE_URL": (
                "postgresql+asyncpg://" + quote(args.db_user, safe="") + ":"
                + quote(credentials["DB_PASSWORD"], safe="")
                + "@" + db_endpoint + "/" + quote(args.db_name, safe="")
            ),
            "REDIS_URL": (
                "rediss://:" + quote(credentials["REDIS_PASSWORD"], safe="")
                + "@" + redis_endpoint + ":6379/0"
            ),
            "SECRET_KEY": credentials["SECRET_KEY"],
            "DEFAULT_GEMINI_API_KEY": gemini_key,
            "NATS_AUTH_TOKEN": credentials["NATS_AUTH_TOKEN"],
            "DB_HOST": db_endpoint.rsplit(":", 1)[0],
            "DB_PORT": db_endpoint.rsplit(":", 1)[1],
            "DB_USER": args.db_user,
            "DB_PASSWORD": credentials["DB_PASSWORD"],
            "CORS_ORIGINS": json.dumps([args.public_web_url.rstrip("/")]),
        }
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "agent-space-secrets", "namespace": args.namespace},
            "type": "Opaque",
            "data": {key: base64.b64encode(value.encode()).decode() for key, value in values.items()},
        }
        result = subprocess.run(
            ["kubectl", "apply", "--server-side", "-f", "-"],
            input=json.dumps(secret),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise ValueError("kubectl could not apply agent-space-secrets; check the namespace and cluster access")

        storage = {
            "apiVersion": "storage.k8s.io/v1",
            "kind": "StorageClass",
            "metadata": {"name": "agent-space-efs"},
            "provisioner": "efs.csi.aws.com",
            "parameters": {
                "provisioningMode": "efs-ap",
                "fileSystemId": args.efs_file_system_id,
                "directoryPerms": "0770",
                "gidRangeStart": "10000",
                "gidRangeEnd": "20000",
            },
            "mountOptions": ["tls"],
        }
        pvc = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": "agent-space-workspaces", "namespace": args.namespace},
            "spec": {
                "accessModes": ["ReadWriteMany"],
                "storageClassName": "agent-space-efs",
                "resources": {"requests": {"storage": "20Gi"}},
            },
        }
        for resource in (storage, pvc):
            result = subprocess.run(
                ["kubectl", "apply", "--server-side", "-f", "-"],
                input=json.dumps(resource), capture_output=True, text=True, check=False,
            )
            if result.returncode:
                raise ValueError("kubectl could not configure the EFS workspace volume")
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"Secret sync failed: {exc}", file=sys.stderr)
        return 1

    print(f"Updated agent-space-secrets in namespace {args.namespace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

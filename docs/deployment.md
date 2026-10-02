# Agent Space Deployment & Infrastructure Guide

Agent Space supports deployment across four operational topologies: Local Compose, Production Compose, Kubernetes, and Cloud (AWS & Azure via OpenTofu).

---

## 1. Local Compose Deployment

For local development and functional testing:

```bash
docker compose up -d
```

Services spun up:
- `backend`: FastAPI API server on `http://localhost:8000`
- `worker`: Temporal and agent worker loop
- `frontend`: Next.js web application on `http://localhost:3000`
- `postgres`: PostgreSQL 16 on `5432`
- `redis`: Redis 7 on `6379`
- `temporal`: Temporal Server on `7233` + Web UI on `8233`
- `keycloak`: Keycloak Identity Server on `8080`
- `gitea`: Gitea Git Server on `3001`
- `seaweedfs`: S3-compatible Artifact Store on `9000`

---

## 2. Production Docker Compose

For single-node on-premise production deployments:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Key differences:
- Production multi-stage images (`Dockerfile.backend`, `Dockerfile.worker`, `Dockerfile.frontend`).
- Runs as non-root user `uid 10001:10001`.
- Built-in HTTP healthchecks on all services.
- Strict resource limits on memory and CPU.
- Isolated Docker bridge networks (`internal` vs `public`).

---

## 3. Kubernetes Deployment (`deploy/kubernetes/base`)

The Kubernetes base requires an `agent-space-secrets` Secret in the `agent-space` namespace. It does not include a placeholder Secret. Create the namespace and sync real credentials before applying the workloads:

```bash
kubectl apply -f deploy/kubernetes/base/namespace.yaml
python3 deploy/kubernetes/sync_aws_secrets.py \
  --app-secret-id "$(tofu -chdir=deploy/opentofu/aws output -raw app_secrets_name)" \
  --gemini-secret-id "$(tofu -chdir=deploy/opentofu/aws output -raw default_gemini_api_key_secret_name)" \
  --db-endpoint "$(tofu -chdir=deploy/opentofu/aws output -raw postgresql_endpoint)" \
  --db-name "$(tofu -chdir=deploy/opentofu/aws output -raw postgresql_database_name)" \
  --redis-endpoint "$(tofu -chdir=deploy/opentofu/aws output -raw redis_primary_endpoint)"
kubectl apply -k deploy/kubernetes/base
```

First, add your Gemini API key as the **plain text secret value** of the Secrets Manager secret named by `default_gemini_api_key_secret_name`. The OpenTofu module creates this secret without a value, so use the AWS Secrets Manager console to set its value after provisioning. The sync command requires AWS CLI credentials with `secretsmanager:GetSecretValue` and `kms:Decrypt` for the two secrets, plus `kubectl` access to the target cluster. It sends credentials to `kubectl` on stdin and does not print or store them in a local file. Run it again after credential rotation, then restart the backend and worker Deployments so their environment variables refresh.

The generated app secret contains `DB_PASSWORD`, `REDIS_PASSWORD`, and `SECRET_KEY`. The sync command constructs the backend's `DATABASE_URL` and TLS `REDIS_URL`, and adds `DEFAULT_GEMINI_API_KEY` to the Kubernetes Secret. User-supplied OpenAI, Anthropic, and other agent API keys remain in each user's browser and do not belong in this server Secret. The OpenTofu state still contains the generated database, Redis, and app secrets; protect access to its state backend.

### Manifest Overview:
- `namespace.yaml`: Configured with Pod Security Standards (`pod-security.kubernetes.io/enforce: baseline`).
- `configmap.yaml`: Nonsecret environment configuration. `sync_aws_secrets.py` creates the Kubernetes Secret separately.
- `backend-deployment.yaml`: Replicas with liveness/readiness HTTP probes, CPU/memory requests and limits.
- `worker-deployment.yaml`: Replicas for asynchronous agent tasks with dedicated Temporal queue consumers.
- `frontend-deployment.yaml`: Next.js web tier.
- `network-policies.yaml`: Default-deny ingress policies with explicit whitelist rules.
- `rbac.yaml`: Least-privilege ServiceAccounts and Roles.
- `ingress.yaml`: Ingress controller routing HTTPS traffic to `/api` and frontend.

---

## 4. Multi-Cloud OpenTofu Infrastructure

Automated infrastructure provisioning using **OpenTofu**:

### AWS (`deploy/opentofu/aws`)
- **VPC Module**: Multi-AZ public and private subnets, NAT gateways.
- **EKS Module**: Managed Kubernetes cluster with IAM OIDC provider.
- **RDS Module**: Multi-AZ PostgreSQL 16 instance with automated snapshots and encryption.
- **Storage Module**: S3 bucket for CAS artifact storage with versioning and lifecycle policies.
- **Cache Module**: ElastiCache Redis cluster.
- **Secrets Module**: AWS Secrets Manager storing generated DB, Redis, and app credentials; a separate empty secret is populated with the developer's Gemini API key outside OpenTofu.
- **GPU Module**: Dedicated GPU node groups (`g5.xlarge`) for vLLM local inference.
- **Monitoring Module**: Prometheus scraper and CloudWatch log groups.

Provisioning command:
```bash
cd deploy/opentofu/aws
tofu init && tofu plan && tofu apply
```

### Azure (`deploy/opentofu/azure`)
- **VNet Module**: Virtual network with dedicated subnets for AKS and Database.
- **AKS Module**: Azure Kubernetes Service cluster with system and user node pools.
- **PostgreSQL Module**: Azure Flexible Server PostgreSQL 16.
- **Storage Module**: Azure Blob Storage container with private endpoints.
- **Key Vault Module**: Azure Key Vault for hardware-backed secret management.
- **GPU Module**: GPU-enabled AKS agent pool (`Standard_NV6ads_A10_v5`).
- **Monitoring Module**: Azure Monitor workspace and Container Insights.

Provisioning command:
```bash
cd deploy/opentofu/azure
tofu init && tofu plan && tofu apply
```

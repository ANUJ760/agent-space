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
- Authenticated, persistent NATS JetStream and a schema-managed Temporal server.
- A one-shot Alembic migration container runs before the API starts.

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
  --redis-endpoint "$(tofu -chdir=deploy/opentofu/aws output -raw redis_primary_endpoint)" \
  --efs-file-system-id "$(tofu -chdir=deploy/opentofu/aws output -raw workspace_efs_file_system_id)" \
  --public-web-url "https://app.example.com"

python3 deploy/kubernetes/deploy_aws.py \
  --ecr-repositories-json "$(tofu -chdir=deploy/opentofu/aws output -json ecr_repository_urls)" \
  --hostname app.example.com \
  --image-tag "$GIT_SHA"
```

First, add your Gemini API key as the **plain text secret value** of the Secrets Manager secret named by `default_gemini_api_key_secret_name`. The OpenTofu module creates this secret without a value, so use the AWS Secrets Manager console to set its value after provisioning. The sync command requires AWS CLI credentials with `secretsmanager:GetSecretValue` and `kms:Decrypt` for the two secrets, plus `kubectl` access to the target cluster. It sends credentials to `kubectl` on stdin and does not print or store them in a local file. Run it again after credential rotation, then restart the backend and worker Deployments so their environment variables refresh.

The generated app secret contains `DB_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`, and `NATS_AUTH_TOKEN`. The sync command constructs the backend's `DATABASE_URL` and TLS `REDIS_URL`, adds `DEFAULT_GEMINI_API_KEY`, and creates the EFS StorageClass and shared workspace claim. User-supplied OpenAI, Anthropic, and other agent API keys remain in each user's browser and do not belong in this server Secret. The OpenTofu state contains generated credentials, so store the state in a locked, encrypted backend.

Before running `deploy_aws.py`, push the four images to the ECR repositories returned by OpenTofu using the same immutable Git SHA tag. Install an ingress controller, create the `agent-space-tls` TLS Secret for the selected hostname, and point DNS at the controller load balancer. The deploy script renders the ECR image URLs and hostname into the manifests without writing credentials to disk.

### Manifest Overview:
- `namespace.yaml`: Configured with Pod Security Standards (`pod-security.kubernetes.io/enforce: baseline`).
- `configmap.yaml`: Nonsecret environment configuration. `sync_aws_secrets.py` creates the Kubernetes Secret separately.
- `backend-deployment.yaml`: Replicas with liveness/readiness HTTP probes, CPU/memory requests and limits.
- `worker-deployment.yaml`: Replicas for asynchronous agent tasks with dedicated Temporal queue consumers.
- `collab.yaml`: Authenticated Hocuspocus WebSocket service sharing the EFS project workspace.
- `nats.yaml`: Authenticated JetStream with encrypted EBS persistence.
- `temporal.yaml`: Temporal schema job and server backed by RDS.
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
- **EKS storage add-ons**: Managed EFS and EBS CSI drivers.
- **RDS Module**: Multi-AZ PostgreSQL 16 instance with automated snapshots and encryption.
- **Storage Module**: S3 bucket for CAS artifact storage with versioning and lifecycle policies.
- **Cache Module**: ElastiCache Redis cluster.
- **Workspace Module**: Encrypted EFS shared by humans, collaboration sessions, and agents.
- **ECR repositories**: Immutable, scanned images for all four application services.
- **Secrets Module**: AWS Secrets Manager storing generated DB, Redis, and app credentials; a separate empty secret is populated with the developer's Gemini API key outside OpenTofu.
- **GPU Module**: Dedicated GPU node groups (`g5.xlarge`) for vLLM local inference.
- **Monitoring Module**: Prometheus scraper and CloudWatch log groups.

Provisioning command:
```bash
cd deploy/opentofu/aws
tofu init \
  -backend-config="bucket=YOUR_PRIVATE_STATE_BUCKET" \
  -backend-config="key=agent-space/production.tfstate" \
  -backend-config="region=YOUR_AWS_REGION"
tofu plan -out=production.plan
tofu apply production.plan
```

Create the private, versioned S3 state bucket before initialization and restrict it to deployment administrators. OpenTofu state contains generated database and service credentials.

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

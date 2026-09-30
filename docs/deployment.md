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

Deploy manifests via Kustomize:

```bash
kubectl apply -k deploy/kubernetes/base
```

### Manifest Overview:
- `namespace.yaml`: Configured with Pod Security Standards (`pod-security.kubernetes.io/enforce: baseline`).
- `configmap.yaml` & `secret-template.yaml`: Environment and secret configuration.
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
- **Secrets Module**: AWS Secrets Manager storing DB credentials and OIDC secrets (zero plaintext in outputs).
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

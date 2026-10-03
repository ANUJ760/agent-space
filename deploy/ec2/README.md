# One-host AWS deployment

This deployment uses one EC2 instance, Docker Compose, a private service network, and Caddy for HTTPS. PostgreSQL, Redis, NATS, Temporal and the app run on the same host. No Kubernetes, load balancer, RDS or ElastiCache is required.

1. Point an A record for your app hostname to the Elastic IP output by `deploy/opentofu/aws-ec2`. Caddy obtains the HTTPS certificate once DNS resolves to the instance.
2. Store the Compose `.env` contents as the **SecretString** of `agent-space-ec2/runtime-env` in Secrets Manager. Required values: `APP_DOMAIN`, `PUBLIC_WEB_URL`, `PUBLIC_API_URL`, `PUBLIC_COLLAB_URL`, `SECRET_KEY`, `DB_PASSWORD`, `TEMPORAL_DB_PASSWORD`, `NATS_AUTH_TOKEN`, `DEFAULT_GEMINI_API_KEY`, and `WORKSPACE_HOST_PATH=./var/workspaces`. Use `https://APP_DOMAIN` for both public web and API URLs and `wss://APP_DOMAIN/collab` for collaboration.
3. Run `deploy/ec2/deploy.sh GIT_SHA` on the instance through Systems Manager Run Command. The instance role can read only the runtime environment secret. The script pulls source from the public repository, writes `.env` with mode 0600, and starts Compose.
4. Check `https://APP_DOMAIN/api/v1/health/ready` and the frontend. Back up the Docker volumes and `/opt/agent-space/var/workspaces` before deleting or rebuilding the instance: the encrypted root disk is deleted when the instance is terminated.

The OpenTofu state for this host uses `agent-space/ec2.tfstate`, separate from the earlier EKS state. `tofu destroy` in `deploy/opentofu/aws-ec2` removes the host, its Elastic IP and its runtime secret. It also deletes the host's PostgreSQL data and project files, so take a backup first.

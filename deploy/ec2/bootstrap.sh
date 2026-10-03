#!/bin/bash
set -euo pipefail

dnf install -y docker git curl
systemctl enable --now docker

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v5.5.1/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version

mkdir -p /opt/agent-space/var/workspaces
chown -R 10001:10001 /opt/agent-space/var/workspaces

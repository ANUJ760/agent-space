#!/bin/bash
set -euo pipefail

APP_DIR=/opt/agent-space
REGION=ap-south-1
SECRET_ID=agent-space-ec2/runtime-env
REPOSITORY=https://github.com/ANUJ760/agent-space.git
REVISION=${1:?Pass the Git revision to deploy}

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPOSITORY" "$APP_DIR"
fi

git -C "$APP_DIR" fetch --depth=1 origin "$REVISION"
git -C "$APP_DIR" checkout --detach FETCH_HEAD

umask 077
aws secretsmanager get-secret-value \
  --region "$REGION" \
  --secret-id "$SECRET_ID" \
  --query SecretString \
  --output text > "$APP_DIR/.env.new"
if ! grep -q '^APP_DOMAIN=[^.].*\.' "$APP_DIR/.env.new"; then
  rm -f "$APP_DIR/.env.new"
  echo 'APP_DOMAIN must be a configured DNS name.' >&2
  exit 1
fi
mv "$APP_DIR/.env.new" "$APP_DIR/.env"
chmod 0600 "$APP_DIR/.env"

mkdir -p "$APP_DIR/var/workspaces"
chown -R 10001:10001 "$APP_DIR/var/workspaces"

cd "$APP_DIR"
docker compose -f docker-compose.prod.yml -f docker-compose.ec2.yml up -d --build --remove-orphans
docker compose -f docker-compose.prod.yml -f docker-compose.ec2.yml ps

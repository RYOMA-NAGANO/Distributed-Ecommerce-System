#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$ROOT_DIR/.docker-migration-backup/$(date +%Y%m%d-%H%M%S)"

log() {
  printf '\n==> %s\n' "$*"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

need_cmd sudo
need_cmd tee

log "Creating backup directory: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

if command -v docker >/dev/null 2>&1; then
  log "Saving current snap Docker inventory"
  docker ps -a --no-trunc >"$BACKUP_DIR/docker-ps-a.txt" 2>&1 || true
  docker volume ls >"$BACKUP_DIR/docker-volume-ls.txt" 2>&1 || true
  docker image ls >"$BACKUP_DIR/docker-image-ls.txt" 2>&1 || true
  docker network ls >"$BACKUP_DIR/docker-network-ls.txt" 2>&1 || true
  docker inspect portainer >"$BACKUP_DIR/portainer.inspect.json" 2>&1 || true

  log "Disabling Portainer auto-restart if it exists"
  docker update --restart=no portainer >/dev/null 2>&1 || true
fi

if [ -d /var/snap/docker/common/var-lib-docker/volumes/portainer_data/_data ]; then
  log "Backing up Portainer volume data"
  sudo tar -C /var/snap/docker/common/var-lib-docker/volumes \
    -czf "$BACKUP_DIR/portainer_data.tgz" portainer_data
fi

log "Removing snap Docker"
if snap list docker >/dev/null 2>&1; then
  sudo snap remove docker
else
  printf 'snap Docker is not installed; continuing.\n'
fi

log "Removing conflicting distro Docker packages if present"
CONFLICTING_PACKAGES="$(dpkg --get-selections \
  docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc \
  2>/dev/null | awk '{print $1}')"
if [ -n "$CONFLICTING_PACKAGES" ]; then
  sudo apt-get remove -y $CONFLICTING_PACKAGES
else
  printf 'No conflicting apt packages found.\n'
fi

log "Installing prerequisites for Docker's official apt repository"
sudo apt-get update
sudo apt-get install -y ca-certificates curl

log "Adding Docker's official GPG key and apt source"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

UBUNTU_SUITE="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
ARCH="$(dpkg --print-architecture)"
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $UBUNTU_SUITE
Components: stable
Architectures: $ARCH
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update

log "Installing official Docker Engine and Compose plugin"
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

log "Enabling Docker services"
sudo systemctl enable --now docker.service containerd.service

log "Allowing current user to run Docker without sudo"
if ! getent group docker >/dev/null; then
  sudo groupadd docker
fi
sudo usermod -aG docker "$USER"

log "Verifying Docker Engine"
sudo docker version
sudo docker compose version

if [ -f "$BACKUP_DIR/portainer_data.tgz" ]; then
  log "Restoring Portainer volume"
  sudo docker volume create portainer_data >/dev/null
  PORTAINER_MOUNT="$(sudo docker volume inspect portainer_data --format '{{.Mountpoint}}')"
  sudo tar -C "$PORTAINER_MOUNT" -xzf "$BACKUP_DIR/portainer_data.tgz" --strip-components=1

  log "Recreating Portainer"
  sudo docker rm -f portainer >/dev/null 2>&1 || true
  sudo docker run -d \
    --name portainer \
    --restart=always \
    -p 18000:8000 \
    -p 19000:9000 \
    -p 19443:9443 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v portainer_data:/data \
    portainer/portainer-ce:latest
fi

log "Done"
printf 'Backup directory: %s\n' "$BACKUP_DIR"
printf 'Log out and log back in, or run: newgrp docker\n'

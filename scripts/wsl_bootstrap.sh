#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f pyproject.toml ]]; then
  echo "Run this script from the repository root." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release software-properties-common

if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
  sudo chmod a+r /etc/apt/keyrings/docker.asc
fi

. /etc/os-release
docker_codename="${VERSION_CODENAME:-noble}"
docker_list="/etc/apt/sources.list.d/docker.list"
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${docker_codename} stable" | sudo tee "${docker_list}" >/dev/null

sudo apt-get update
sudo apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin \
  postgresql-client \
  redis-tools \
  python3.12 \
  python3.12-venv \
  python3-pip

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files docker.service >/dev/null 2>&1; then
  sudo systemctl enable --now docker || true
fi
if ! sudo docker ps >/dev/null 2>&1; then
  sudo service docker start || true
fi

if ! groups "${USER}" | grep -qE '(^| )docker( |$)'; then
  sudo usermod -aG docker "${USER}" || true
  echo "User ${USER} added to docker group. Current shell may still require sudo docker until WSL is restarted."
fi

python3.12 -m venv .venv-linux
. .venv-linux/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

docker --version
docker compose version
sudo docker ps >/dev/null
python3.12 --version
python -m pytest --version
python -m pytest

echo "WSL bootstrap verification completed."

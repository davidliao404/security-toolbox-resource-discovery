#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f pyproject.toml ]]; then
  echo "Run this script from the repository root." >&2
  exit 1
fi

echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4 >/dev/null

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release software-properties-common

docker_repo_ready=0
if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
  sudo install -m 0755 -d /etc/apt/keyrings
  if curl --retry 5 --retry-delay 5 --connect-timeout 20 -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null; then
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    docker_repo_ready=1
  else
    sudo rm -f /etc/apt/keyrings/docker.asc
    echo "Docker official repository key download failed; falling back to Ubuntu docker packages." >&2
  fi
else
  docker_repo_ready=1
fi

. /etc/os-release
docker_codename="${VERSION_CODENAME:-noble}"
docker_list="/etc/apt/sources.list.d/docker.list"
if [[ "${docker_repo_ready}" == "1" ]]; then
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${docker_codename} stable" | sudo tee "${docker_list}" >/dev/null
else
  sudo rm -f "${docker_list}"
fi

sudo apt-get update
if [[ "${docker_repo_ready}" == "1" ]]; then
  sudo apt-get remove -y docker-compose-v2 docker-buildx docker.io containerd runc || true
  sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
else
  sudo apt-get install -y \
    docker.io \
    docker-buildx \
    docker-compose-v2
fi

sudo apt-get install -y \
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

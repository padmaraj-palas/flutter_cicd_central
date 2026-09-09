#!/usr/bin/env bash
# Read-only checks. Run from Linux or an integrated WSL2 distribution.
set -euo pipefail
allow_existing=false
if [[ "${1:-}" == "--allow-existing" && "$#" -eq 1 ]]; then
  allow_existing=true
elif [[ "$#" -ne 0 ]]; then
  echo "Usage: bash check-host.sh [--allow-existing]" >&2
  exit 2
fi
command -v docker >/dev/null || { echo "Docker CLI is missing." >&2; exit 1; }
docker info >/dev/null
docker compose version
os_type="$(docker info --format '{{.OSType}}')"
architecture="$(docker info --format '{{.Architecture}}')"
[[ "$os_type" == "linux" ]] || { echo "Switch Docker to Linux containers." >&2; exit 1; }
case "$architecture" in
  x86_64|amd64) ;;
  *) echo "This starter requires an amd64 Docker host; found $architecture." >&2; exit 1 ;;
esac
[[ -S /var/run/docker.sock ]] || {
  echo "Expected /var/run/docker.sock. Use the local Linux daemon or WSL2 Docker Desktop integration." >&2
  exit 1
}
# Compose mounts this local socket. Confirm that the CLI is using the same daemon.
selected_id="$(docker info --format '{{.ID}}')"
socket_id="$(docker --host unix:///var/run/docker.sock info --format '{{.ID}}')"
[[ "$selected_id" == "$socket_id" ]] || {
  echo "Selected Docker context differs from /var/run/docker.sock." >&2
  exit 1
}
script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker compose -f "$script_root/compose.yaml" --profile tools config --quiet
if docker container inspect jenkins >/dev/null 2>&1; then
  if [[ "$allow_existing" != true ]]; then
    echo "Container 'jenkins' already exists. This new-host setup must not replace it." >&2
    echo "Use --allow-existing for read-only diagnostics only; see documents/SETUP_LINUX.md or documents/SETUP_WINDOWS_WSL.md in the central repository." >&2
    exit 1
  fi
  echo "Existing Jenkins detected; diagnostic mode only."
fi
docker info --format 'Docker host: {{.OSType}}/{{.Architecture}}, CPUs={{.NCPU}}, RAM bytes={{.MemTotal}}'
docker system df
echo "Host checks passed. No containers or host settings were changed."

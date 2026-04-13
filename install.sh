#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="${SERVICE_NAME:-hermes-controlplane.service}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CONTROLPLANE_HOST="${CONTROLPLANE_HOST:-127.0.0.1}"
CONTROLPLANE_PORT="${CONTROLPLANE_PORT:-8780}"
CONTROLPLANE_LOG_LEVEL="${CONTROLPLANE_LOG_LEVEL:-info}"
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
SERVICE_TEMPLATE="${ROOT_DIR}/contrib/systemd/hermes-controlplane.service.example"
SERVICE_TARGET="${SYSTEMD_DIR}/${SERVICE_NAME}"

if [[ -z "${UV_BIN}" ]]; then
  echo "error: uv is required but was not found in PATH" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "error: systemctl is required for the official install flow" >&2
  exit 1
fi

mkdir -p "${SYSTEMD_DIR}"
cd "${ROOT_DIR}"

if [[ ! -f .env ]]; then
  cat > .env <<EOF
HERMES_HOME=${HERMES_HOME}
CONTROLPLANE_HOST=${CONTROLPLANE_HOST}
CONTROLPLANE_PORT=${CONTROLPLANE_PORT}
CONTROLPLANE_LOG_LEVEL=${CONTROLPLANE_LOG_LEVEL}
EOF
  echo "created .env"
else
  echo ".env already exists, keeping it as-is"
fi

"${UV_BIN}" sync

sed \
  -e "s|__WORKDIR__|${ROOT_DIR}|g" \
  -e "s|__HERMES_HOME__|${HERMES_HOME}|g" \
  -e "s|__HOST__|${CONTROLPLANE_HOST}|g" \
  -e "s|__PORT__|${CONTROLPLANE_PORT}|g" \
  -e "s|__LOG_LEVEL__|${CONTROLPLANE_LOG_LEVEL}|g" \
  -e "s|__UV_BIN__|${UV_BIN}|g" \
  "${SERVICE_TEMPLATE}" > "${SERVICE_TARGET}"

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}"

echo

echo "Hermes Control Plane installed."
echo "Local URL: http://${CONTROLPLANE_HOST}:${CONTROLPLANE_PORT}"
echo
if [[ "${CONTROLPLANE_HOST}" == "127.0.0.1" ]]; then
  echo "Recommended remote access:"
  echo "  ssh -L ${CONTROLPLANE_PORT}:127.0.0.1:${CONTROLPLANE_PORT} your-user@your-server"
  echo
fi
echo "Tailscale can be used as an advanced private-network option when needed."

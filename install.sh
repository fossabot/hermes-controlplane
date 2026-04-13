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
PLATFORM="$(uname -s)"
ACTION="${1:-install}"

usage() {
  cat <<EOF
Usage: ./install.sh [install|uninstall]

Commands:
  install     Install Hermes Control Plane as a user service (default)
  uninstall   Stop, disable, and remove the user service

Notes:
  - The official install flow is Linux-only because it depends on systemd --user.
  - On macOS, use the manual run instructions in docs/install-host-native.md.
EOF
}

require_uv() {
  if [[ -z "${UV_BIN}" ]]; then
    echo "error: uv is required but was not found in PATH" >&2
    exit 1
  fi
}

require_linux_systemd() {
  if [[ "${PLATFORM}" != "Linux" ]]; then
    echo "error: the official installer currently supports Linux only (systemd --user required)" >&2
    echo "hint: on ${PLATFORM}, use the manual instructions in docs/install-host-native.md" >&2
    exit 1
  fi

  if ! command -v systemctl >/dev/null 2>&1; then
    echo "error: systemctl is required for the official install flow" >&2
    exit 1
  fi
}

install_service() {
  require_uv
  require_linux_systemd

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
}

uninstall_service() {
  require_linux_systemd

  if systemctl --user list-unit-files "${SERVICE_NAME}" >/dev/null 2>&1; then
    systemctl --user disable --now "${SERVICE_NAME}" || true
  else
    systemctl --user stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
  fi

  rm -f "${SERVICE_TARGET}"
  systemctl --user daemon-reload
  systemctl --user reset-failed >/dev/null 2>&1 || true

  echo "Hermes Control Plane service removed from systemd user units."
  echo "Project files, virtual environment, and .env were left in place."
  echo "If you want a full cleanup, remove them manually:"
  echo "  rm -rf ${ROOT_DIR}/.venv ${ROOT_DIR}/.env"
}

case "${ACTION}" in
  install)
    install_service
    ;;
  uninstall)
    uninstall_service
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "error: unknown action '${ACTION}'" >&2
    usage >&2
    exit 1
    ;;
esac

#!/usr/bin/env bash
# install-bridge.sh — Deploy and start the ESP32 bridge service
#
# Usage:
#   ./scripts/install-bridge.sh [--mode http|mqtt|both] [options]
#
# Options:
#   --mode http|mqtt|both     Running mode (default: http)
#   --host <HOST>             HTTP listen host (default: 0.0.0.0)
#   --port <PORT>             HTTP listen port (default: 7070)
#   --mqtt-broker <HOST>      MQTT broker address (required for mqtt/both)
#   --mqtt-port <PORT>        MQTT broker port (default: 1883)
#   --mqtt-username <USER>    MQTT username
#   --mqtt-password <PASS>    MQTT password
#   --device-id <ID>          Device ID (default: esp32-1)
#   --start                   Start the service after install

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

TOOLS_DIR="${HOME}/.openclaw/tools/mstodo"
STATE_DIR="${HOME}/.openclaw/state/mstodo"
BRIDGE_ENV="${STATE_DIR}/bridge.env"

# Defaults
MODE="http"
HOST="0.0.0.0"
PORT="7070"
MQTT_BROKER=""
MQTT_PORT="1883"
MQTT_USERNAME=""
MQTT_PASSWORD=""
DEVICE_ID="esp32-1"
DO_START=true  # default: start after install

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode) MODE="$2"; shift 2 ;;
        --host) HOST="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --mqtt-broker) MQTT_BROKER="$2"; shift 2 ;;
        --mqtt-port) MQTT_PORT="$2"; shift 2 ;;
        --mqtt-username) MQTT_USERNAME="$2"; shift 2 ;;
        --mqtt-password) MQTT_PASSWORD="$2"; shift 2 ;;
        --device-id) DEVICE_ID="$2"; shift 2 ;;
        --start) DO_START=true; shift ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

echo "=== mstodo ESP32 Bridge Installer ==="
echo ""

# 1. Deploy project
echo "[1/4] Deploying project to ${TOOLS_DIR} ..."
mkdir -p "$TOOLS_DIR"
rsync -a --delete \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.venv' \
    --exclude '*.pyc' \
    "$PROJECT_DIR/" "$TOOLS_DIR/"
echo "  Done."

# 2. Install dependencies
echo "[2/4] Installing dependencies ..."
if command -v uv &>/dev/null; then
    uv sync --project "$TOOLS_DIR"
    PYTHON_BIN="${TOOLS_DIR}/.venv/bin/python"
    if [[ ! -x "$PYTHON_BIN" ]]; then
        echo "  WARNING: venv python not found at ${PYTHON_BIN}, falling back to uv run" >&2
        PYTHON_BIN="uv run python"
    fi
else
    echo "  WARNING: uv not found, using system python (may fail)" >&2
    PYTHON_BIN="python3"
fi
echo "  Done."

# 3. Generate bridge.env
echo "[3/4] Generating bridge config: ${BRIDGE_ENV} ..."
mkdir -p "$STATE_DIR"

case "$MODE" in
    http)
        CMD="${PYTHON_BIN} -m bridge.mstodo_bridge.daemon http --host ${HOST} --port ${PORT}"
        ;;
    mqtt)
        if [[ -z "$MQTT_BROKER" ]]; then
            echo "ERROR: --mqtt-broker is required for mqtt mode" >&2
            exit 1
        fi
        CMD="${PYTHON_BIN} -m bridge.mstodo_bridge.daemon mqtt --mqtt-broker ${MQTT_BROKER} --mqtt-port ${MQTT_PORT} --device-id ${DEVICE_ID}"
        [[ -n "$MQTT_USERNAME" ]] && CMD+=" --mqtt-username ${MQTT_USERNAME}"
        [[ -n "$MQTT_PASSWORD" ]] && CMD+=" --mqtt-password ${MQTT_PASSWORD}"
        ;;
    both)
        if [[ -z "$MQTT_BROKER" ]]; then
            echo "ERROR: --mqtt-broker is required for both mode" >&2
            exit 1
        fi
        CMD="${PYTHON_BIN} -m bridge.mstodo_bridge.daemon both --host ${HOST} --port ${PORT} --mqtt-broker ${MQTT_BROKER} --mqtt-port ${MQTT_PORT} --device-id ${DEVICE_ID}"
        [[ -n "$MQTT_USERNAME" ]] && CMD+=" --mqtt-username ${MQTT_USERNAME}"
        [[ -n "$MQTT_PASSWORD" ]] && CMD+=" --mqtt-password ${MQTT_PASSWORD}"
        ;;
    *)
        echo "ERROR: Invalid mode: ${MODE}" >&2
        exit 1
        ;;
esac

cat > "$BRIDGE_ENV" <<EOF
BRIDGE_CMD=${CMD}
EOF
chmod 600 "$BRIDGE_ENV"
echo "  Done."

# 4. Install systemd service
echo "[4/4] Installing systemd user service ..."
mkdir -p "${HOME}/.config/systemd/user"
cp "${PROJECT_DIR}/service/mstodo-bridge.service" "${HOME}/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable mstodo-bridge
echo "  Done."

if $DO_START; then
    echo ""
    echo "Starting bridge ..."
    systemctl --user restart mstodo-bridge
    sleep 1
    systemctl --user status mstodo-bridge --no-pager || true
fi

echo ""
echo "=== Bridge installation complete ==="
echo ""
echo "Commands:"
echo "  systemctl --user start mstodo-bridge"
echo "  systemctl --user stop mstodo-bridge"
echo "  journalctl --user -u mstodo-bridge -f"

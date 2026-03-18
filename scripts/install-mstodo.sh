#!/usr/bin/env bash
# install-mstodo.sh — Deploy mstodo skill and install dependencies
#
# Usage:
#   ./scripts/install-mstodo.sh [--workspace <path>]
#
# What it does:
#   1. Copies skills/mstodo/ to the OpenClaw workspace
#   2. Runs `uv sync` to install Python dependencies
#   3. Creates state directory for tokens

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Defaults
WORKSPACE="${HOME}/.openclaw/workspace"
LEGACY_WORKSPACE="${HOME}/.openclaw/workspace/skills"
STATE_DIR="${HOME}/.openclaw/state/mstodo"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workspace)
            WORKSPACE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [--workspace <path>]" >&2
            exit 1
            ;;
    esac
done

echo "=== mstodo Skill Installer ==="
echo ""

if [[ ! -d "$WORKSPACE" && -d "$LEGACY_WORKSPACE" ]]; then
    WORKSPACE="${HOME}/.openclaw/workspace"
fi

# 1. Install/copy skill
SKILL_SRC="${PROJECT_DIR}/skills/mstodo"
SKILL_DST="${WORKSPACE}/skills/mstodo"

if [[ ! -d "$SKILL_SRC" ]]; then
    echo "ERROR: Skill source not found: ${SKILL_SRC}" >&2
    exit 1
fi

echo "[1/3] Copying skill to ${SKILL_DST} ..."
mkdir -p "$(dirname "$SKILL_DST")"
rm -rf "$SKILL_DST"
cp -a "$SKILL_SRC" "$SKILL_DST"

if [[ -d "${HOME}/.openclaw/workspace/skills" ]]; then
    LEGACY_SKILL_DST="${HOME}/.openclaw/workspace/skills/mstodo"
    if [[ "$LEGACY_SKILL_DST" != "$SKILL_DST" ]]; then
        rm -rf "$LEGACY_SKILL_DST"
        cp -a "$SKILL_SRC" "$LEGACY_SKILL_DST"
    fi
fi
echo "  Done."

# 2. Install dependencies
echo "[2/3] Installing Python dependencies ..."

# Find uv in common locations
UV_BIN=""
if command -v uv &>/dev/null; then
    UV_BIN="uv"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
    UV_BIN="${HOME}/.local/bin/uv"
elif [[ -x "${HOME}/.cargo/bin/uv" ]]; then
    UV_BIN="${HOME}/.cargo/bin/uv"
fi

if [[ -n "$UV_BIN" ]]; then
    "$UV_BIN" sync --project "$PROJECT_DIR"
    echo "  Done."
else
    echo "  WARNING: uv not found in PATH, ~/.local/bin, or ~/.cargo/bin" >&2
    echo "  Install uv first: https://docs.astral.sh/uv/" >&2
    echo "  Skipping dependency install." >&2
fi

# 3. Create state directory
echo "[3/3] Creating state directory ..."
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
echo "  Done: ${STATE_DIR}"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Set MS_TODO_CLIENT_ID in ~/.openclaw/openclaw.json"
echo "  2. Restart OpenClaw"
echo "  3. Say '开始 ToDo 授权' in chat to authenticate"

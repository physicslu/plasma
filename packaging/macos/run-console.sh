#!/bin/sh
set -eu

PRODUCT_ROOT="/Library/Application Support/Plasma"
CURRENT_ROOT="$PRODUCT_ROOT/current"
INSTALL_ROOT="$PRODUCT_ROOT/install"
NODE_PATH_FILE="$INSTALL_ROOT/node-path"
USER_DATA_ROOT="$HOME/Library/Application Support/Plasma"
ALIAS_PATH="$USER_DATA_ROOT/config/selected-ppu-alias"
LOG_ROOT="$HOME/Library/Logs/Plasma"
LOG_PATH="$LOG_ROOT/console.log"

if [ ! -r "$NODE_PATH_FILE" ]; then
  echo "Plasma Console Node.js runtime path is missing: $NODE_PATH_FILE" >&2
  exit 78
fi

NODE_PATH="$(cat "$NODE_PATH_FILE")"
if [ ! -x "$NODE_PATH" ]; then
  echo "Plasma Console Node.js runtime is not executable: $NODE_PATH" >&2
  exit 78
fi
if [ ! -f "$CURRENT_ROOT/runtime/console/server.js" ]; then
  echo "Plasma Console runtime payload is missing" >&2
  exit 78
fi

SELECTED_ALIAS=""
if [ -r "$ALIAS_PATH" ]; then
  SELECTED_ALIAS="$(tr -d '\r\n' < "$ALIAS_PATH")"
fi

mkdir -p "$LOG_ROOT"
export HOST="127.0.0.1"
export PORT="18000"
export PLASMA_FLEET_UI_ENABLED="1"
export PLASMA_CONTROL_STATION_MODE="managed"
export PLASMA_MANAGER_API_URL="http://127.0.0.1:18180"
export PLASMA_MANAGER_PPU_ALIAS="$SELECTED_ALIAS"

cd "$CURRENT_ROOT/runtime/console"
exec "$NODE_PATH" "$CURRENT_ROOT/runtime/console/server.js" >>"$LOG_PATH" 2>&1

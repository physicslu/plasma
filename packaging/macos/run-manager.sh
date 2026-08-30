#!/bin/sh
set -eu

PRODUCT_ROOT="/Library/Application Support/Plasma"
CURRENT_ROOT="$PRODUCT_ROOT/current"
INSTALL_ROOT="$PRODUCT_ROOT/install"
PYTHON_PATH_FILE="$INSTALL_ROOT/python-path"
USER_DATA_ROOT="$HOME/Library/Application Support/Plasma"
CONFIG_PATH="$USER_DATA_ROOT/config/manager.yaml"
LOG_ROOT="$HOME/Library/Logs/Plasma"
LOG_PATH="$LOG_ROOT/manager.log"

if [ ! -r "$PYTHON_PATH_FILE" ]; then
  echo "Plasma Manager runtime path is missing: $PYTHON_PATH_FILE" >&2
  exit 78
fi

PYTHON_PATH="$(cat "$PYTHON_PATH_FILE")"
if [ ! -x "$PYTHON_PATH" ]; then
  echo "Plasma Manager Python runtime is not executable: $PYTHON_PATH" >&2
  exit 78
fi
if [ ! -f "$CURRENT_ROOT/runtime/manager/manager.pyz" ]; then
  echo "Plasma Manager runtime payload is missing" >&2
  exit 78
fi
if [ ! -f "$CONFIG_PATH" ]; then
  echo "Plasma Manager configuration is missing: $CONFIG_PATH" >&2
  exit 78
fi

mkdir -p "$USER_DATA_ROOT/state" "$LOG_ROOT"
exec "$PYTHON_PATH" "$CURRENT_ROOT/runtime/manager/manager.pyz" \
  --config "$CONFIG_PATH" >>"$LOG_PATH" 2>&1

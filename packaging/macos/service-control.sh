#!/bin/sh
set -eu

PRODUCT_ROOT="/Library/Application Support/Plasma"
CURRENT_ROOT="$PRODUCT_ROOT/current"

detect_user() {
  if [ -n "${PLASMA_INSTALL_USER:-}" ] && /usr/bin/id "$PLASMA_INSTALL_USER" >/dev/null 2>&1; then
    printf '%s\n' "$PLASMA_INSTALL_USER"
    return
  fi
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ] && /usr/bin/id "$SUDO_USER" >/dev/null 2>&1; then
    printf '%s\n' "$SUDO_USER"
    return
  fi
  console_user="$(/usr/bin/stat -f '%Su' /dev/console 2>/dev/null || true)"
  if [ -n "$console_user" ] && [ "$console_user" != "root" ] && [ "$console_user" != "loginwindow" ]; then
    printf '%s\n' "$console_user"
    return
  fi
  /usr/bin/dscl . -list /Users UniqueID 2>/dev/null | \
    /usr/bin/awk '$2 >= 500 && $1 !~ /^_/ { print $1; exit }'
}

user_home() {
  /usr/bin/dscl . -read "/Users/$1" NFSHomeDirectory 2>/dev/null | \
    /usr/bin/awk '{ print $2 }'
}

USER_NAME="$(detect_user)"
if [ -z "$USER_NAME" ]; then
  echo "Cannot determine Plasma Control Station user" >&2
  exit 64
fi
USER_ID="$(/usr/bin/id -u "$USER_NAME")"
HOME_DIR="$(user_home "$USER_NAME")"
if [ -z "$HOME_DIR" ] || [ ! -d "$HOME_DIR" ]; then
  echo "Cannot determine home directory for $USER_NAME" >&2
  exit 64
fi

MANAGER_PLIST="$HOME_DIR/Library/LaunchAgents/com.plasma.manager.plist"
CONSOLE_PLIST="$HOME_DIR/Library/LaunchAgents/com.plasma.console.plist"
DOMAIN="gui/$USER_ID"

bootout_label() {
  label="$1"
  /bin/launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
}

bootstrap_plist() {
  plist="$1"
  label="$2"
  if [ ! -f "$plist" ]; then
    echo "Missing LaunchAgent: $plist" >&2
    exit 66
  fi
  /bin/launchctl bootstrap "$DOMAIN" "$plist"
  /bin/launchctl enable "$DOMAIN/$label" >/dev/null 2>&1 || true
  /bin/launchctl kickstart -k "$DOMAIN/$label"
}

case "${1:-}" in
  start)
    bootout_label com.plasma.console
    bootout_label com.plasma.manager
    bootstrap_plist "$MANAGER_PLIST" com.plasma.manager
    bootstrap_plist "$CONSOLE_PLIST" com.plasma.console
    ;;
  stop)
    bootout_label com.plasma.console
    bootout_label com.plasma.manager
    ;;
  restart)
    "$CURRENT_ROOT/bin/service-control.sh" stop
    "$CURRENT_ROOT/bin/service-control.sh" start
    ;;
  status)
    /bin/launchctl print "$DOMAIN/com.plasma.manager"
    /bin/launchctl print "$DOMAIN/com.plasma.console"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 64
    ;;
esac

#!/bin/sh
set -eu

PRODUCT_ROOT="/Library/Application Support/Plasma"
PACKAGE_ID="com.plasma.control-station"
TARGET_USER=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --user)
      shift
      TARGET_USER="${1:-}"
      ;;
    *)
      echo "Usage: $0 [--user USER]" >&2
      exit 64
      ;;
  esac
  shift
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Plasma pilot uninstall must run as root (use sudo)." >&2
  exit 77
fi

if [ -z "$TARGET_USER" ]; then
  TARGET_USER="${SUDO_USER:-}"
fi
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
  TARGET_USER="$(/usr/bin/stat -f '%Su' /dev/console 2>/dev/null || true)"
fi
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ] || [ "$TARGET_USER" = "loginwindow" ]; then
  TARGET_USER="$(/usr/bin/dscl . -list /Users UniqueID 2>/dev/null | /usr/bin/awk '$2 >= 500 && $1 !~ /^_/ { print $1; exit }')"
fi
if [ -z "$TARGET_USER" ] || ! /usr/bin/id "$TARGET_USER" >/dev/null 2>&1; then
  echo "Cannot determine uninstall target user" >&2
  exit 64
fi

TARGET_UID="$(/usr/bin/id -u "$TARGET_USER")"
TARGET_HOME="$(/usr/bin/dscl . -read "/Users/$TARGET_USER" NFSHomeDirectory 2>/dev/null | /usr/bin/awk '{ print $2 }')"
DOMAIN="gui/$TARGET_UID"

for label in com.plasma.console com.plasma.manager; do
  /bin/launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
done

rm -f \
  "$TARGET_HOME/Library/LaunchAgents/com.plasma.manager.plist" \
  "$TARGET_HOME/Library/LaunchAgents/com.plasma.console.plist"

rm -rf "$PRODUCT_ROOT/releases" "$PRODUCT_ROOT/current" "$PRODUCT_ROOT/install"
rmdir "$PRODUCT_ROOT" >/dev/null 2>&1 || true
/usr/sbin/pkgutil --forget "$PACKAGE_ID" >/dev/null 2>&1 || true

echo "Plasma Control Station pilot runtime removed."
echo "User config/state/logs were preserved under $TARGET_HOME/Library."

#!/bin/sh
set -eu

PRODUCT_ROOT="/Library/Application Support/Plasma"
VERSION="__PLASMA_VERSION__"
RELEASE_ROOT="$PRODUCT_ROOT/releases/$VERSION"
INSTALL_ROOT="$PRODUCT_ROOT/install"

fail() {
  echo "Plasma Control Station installer: $*" >&2
  exit 1
}

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

version_ge() {
  value="$(printf '%s' "$1" | /usr/bin/sed 's/^[^0-9]*//')"
  major="$(printf '%s' "$value" | /usr/bin/awk -F. '{print $1+0}')"
  minor="$(printf '%s' "$value" | /usr/bin/awk -F. '{print $2+0}')"
  patch="$(printf '%s' "$value" | /usr/bin/awk -F. '{print $3+0}')"
  req_major="$2"
  req_minor="$3"
  req_patch="$4"
  [ "$major" -gt "$req_major" ] && return 0
  [ "$major" -lt "$req_major" ] && return 1
  [ "$minor" -gt "$req_minor" ] && return 0
  [ "$minor" -lt "$req_minor" ] && return 1
  [ "$patch" -ge "$req_patch" ]
}

resolve_python() {
  home="$1"
  for candidate in \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /usr/bin/python3 \
    "$home"/.pyenv/versions/*/bin/python3
  do
    [ -x "$candidate" ] || continue
    version="$("$candidate" -c 'import sys; print(".".join(str(v) for v in sys.version_info[:3]))' 2>/dev/null || true)"
    [ -n "$version" ] || continue
    if version_ge "$version" 3 11 0; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

resolve_node() {
  home="$1"
  for candidate in \
    /opt/homebrew/bin/node \
    /usr/local/bin/node \
    /usr/bin/node \
    "$home"/.nvm/versions/node/*/bin/node
  do
    [ -x "$candidate" ] || continue
    version="$("$candidate" --version 2>/dev/null || true)"
    [ -n "$version" ] || continue
    if version_ge "$version" 22 13 0; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

[ "$(id -u)" -eq 0 ] || fail "postinstall must run as root"
[ -d "$RELEASE_ROOT/runtime" ] || fail "runtime payload missing from $RELEASE_ROOT"
[ -x "$RELEASE_ROOT/bin/run-manager.sh" ] || fail "Manager launch wrapper missing"
[ -x "$RELEASE_ROOT/bin/run-console.sh" ] || fail "Console launch wrapper missing"

INSTALL_USER="$(detect_user)"
[ -n "$INSTALL_USER" ] || fail "cannot determine the operator user"
INSTALL_UID="$(/usr/bin/id -u "$INSTALL_USER")"
INSTALL_GROUP="$(/usr/bin/id -gn "$INSTALL_USER")"
INSTALL_HOME="$(user_home "$INSTALL_USER")"
[ -n "$INSTALL_HOME" ] && [ -d "$INSTALL_HOME" ] || fail "cannot determine home for $INSTALL_USER"

PYTHON_PATH="$(resolve_python "$INSTALL_HOME" || true)"
[ -n "$PYTHON_PATH" ] || fail "Python >= 3.11 not found in stable Homebrew/system/pyenv locations"
NODE_PATH="$(resolve_node "$INSTALL_HOME" || true)"
[ -n "$NODE_PATH" ] || fail "Node.js >= 22.13 not found in stable Homebrew/system/nvm locations"

mkdir -p "$INSTALL_ROOT"
printf '%s\n' "$PYTHON_PATH" > "$INSTALL_ROOT/python-path"
printf '%s\n' "$NODE_PATH" > "$INSTALL_ROOT/node-path"
printf '%s\n' "$INSTALL_USER" > "$INSTALL_ROOT/user"
chmod 0644 "$INSTALL_ROOT/python-path" "$INSTALL_ROOT/node-path" "$INSTALL_ROOT/user"

ln -sfn "$RELEASE_ROOT" "$PRODUCT_ROOT/current"

USER_DATA_ROOT="$INSTALL_HOME/Library/Application Support/Plasma"
USER_CONFIG_ROOT="$USER_DATA_ROOT/config"
USER_STATE_ROOT="$USER_DATA_ROOT/state"
USER_LOG_ROOT="$INSTALL_HOME/Library/Logs/Plasma"
USER_LAUNCH_ROOT="$INSTALL_HOME/Library/LaunchAgents"

install -d -m 0755 -o "$INSTALL_USER" -g "$INSTALL_GROUP" \
  "$USER_DATA_ROOT" "$USER_CONFIG_ROOT" "$USER_STATE_ROOT" "$USER_LOG_ROOT" "$USER_LAUNCH_ROOT"

MANAGER_CONFIG="$USER_CONFIG_ROOT/manager.yaml"
if [ ! -e "$MANAGER_CONFIG" ]; then
  cat > "$MANAGER_CONFIG" <<EOF
manager:
  host: 127.0.0.1
  port: 18180
  request_timeout_s: 2.0
  poll_interval_s: 2.0
  observation_db_path: $USER_STATE_ROOT/manager-observations.sqlite3
  registry_state_path: $USER_STATE_ROOT/manager-registry.json
ppus: []
EOF
  chown "$INSTALL_USER:$INSTALL_GROUP" "$MANAGER_CONFIG"
  chmod 0644 "$MANAGER_CONFIG"
fi

ALIAS_FILE="$USER_CONFIG_ROOT/selected-ppu-alias"
if [ ! -e "$ALIAS_FILE" ]; then
  : > "$ALIAS_FILE"
  chown "$INSTALL_USER:$INSTALL_GROUP" "$ALIAS_FILE"
  chmod 0644 "$ALIAS_FILE"
fi

for plist in com.plasma.manager.plist com.plasma.console.plist; do
  cp "$RELEASE_ROOT/launchd/$plist" "$USER_LAUNCH_ROOT/$plist"
  chown "$INSTALL_USER:$INSTALL_GROUP" "$USER_LAUNCH_ROOT/$plist"
  chmod 0644 "$USER_LAUNCH_ROOT/$plist"
  /usr/bin/plutil -lint "$USER_LAUNCH_ROOT/$plist" >/dev/null || fail "invalid LaunchAgent $plist"
done

DOMAIN="gui/$INSTALL_UID"
for label in com.plasma.console com.plasma.manager; do
  /bin/launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
done

/bin/launchctl bootstrap "$DOMAIN" "$USER_LAUNCH_ROOT/com.plasma.manager.plist" || fail "cannot bootstrap Manager LaunchAgent"
/bin/launchctl enable "$DOMAIN/com.plasma.manager" >/dev/null 2>&1 || true
/bin/launchctl kickstart -k "$DOMAIN/com.plasma.manager" || fail "cannot start Manager LaunchAgent"

/bin/launchctl bootstrap "$DOMAIN" "$USER_LAUNCH_ROOT/com.plasma.console.plist" || fail "cannot bootstrap Console LaunchAgent"
/bin/launchctl enable "$DOMAIN/com.plasma.console" >/dev/null 2>&1 || true
/bin/launchctl kickstart -k "$DOMAIN/com.plasma.console" || fail "cannot start Console LaunchAgent"

echo "Plasma Control Station $VERSION installed for $INSTALL_USER"
echo "Python: $PYTHON_PATH"
echo "Node.js: $NODE_PATH"
exit 0

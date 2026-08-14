#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_DIR="$ROOT_DIR/software/python"
PYTHON_BIN="$PYTHON_DIR/.venv/bin/python"
PLASMA_BIN="$PYTHON_DIR/.venv/bin/plasma"
CONFIG_FILE="${PLASMA_HIL_CONFIG:-$PYTHON_DIR/config/plasma.yaml}"
TIMEOUT_S="${PLASMA_HIL_TIMEOUT_S:-120}"

usage() {
  cat <<'EOF'
Usage:
  PLASMA_HIL_CONFIRM=YES tools/test-hardware.sh CHANNEL FIRMWARE [HOST] [PORT]

Example:
  PLASMA_HIL_CONFIRM=YES tools/test-hardware.sh 0 firmware.bin 127.0.0.1 9900

WARNING: this is a destructive Hardware-in-the-Loop test. It erases and programs
the selected target, verifies it, reads the programmed byte range back, and
compares the read-back bytes with the original firmware.

The script never starts/stops Plasma services and never installs dependencies.
EOF
}

fail() {
  printf '\nERROR: %s\n' "$1" >&2
  exit 1
}

[[ $# -ge 2 && $# -le 4 ]] || { usage; exit 2; }
[[ "${PLASMA_HIL_CONFIRM:-}" == "YES" ]] || fail "Refusing destructive hardware test. Re-run with PLASMA_HIL_CONFIRM=YES after confirming the target/channel is safe to erase."

CHANNEL="$1"
FIRMWARE="$2"
HOST="${3:-127.0.0.1}"
PORT="${4:-9900}"

[[ "$CHANNEL" =~ ^[0-9]+$ ]] || fail "CHANNEL must be a non-negative integer."
[[ -f "$FIRMWARE" ]] || fail "Firmware file not found: $FIRMWARE"
[[ -s "$FIRMWARE" ]] || fail "Firmware file is empty: $FIRMWARE"
[[ -x "$PYTHON_BIN" ]] || fail "Python venv is missing at $PYTHON_BIN."
[[ -x "$PLASMA_BIN" ]] || fail "Plasma CLI is missing at $PLASMA_BIN."
[[ -f "$CONFIG_FILE" ]] || fail "Plasma config not found: $CONFIG_FILE"

FIRMWARE="$($PYTHON_BIN -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$FIRMWARE")"
FIRMWARE_SIZE="$($PYTHON_BIN -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).stat().st_size)' "$FIRMWARE")"

INTERFACE="$($PYTHON_BIN - "$CONFIG_FILE" "$CHANNEL" <<'PY'
import sys
from pathlib import Path
import yaml

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8")) or {}
channel_id = int(sys.argv[2])
for channel in config.get("channels", []):
    if int(channel.get("id", -1)) != channel_id:
        continue
    if not bool(channel.get("enabled", False)):
        raise SystemExit(f"CH{channel_id} is disabled in {sys.argv[1]}")
    interface = str(channel.get("interface", "")).strip()
    if not interface:
        raise SystemExit(f"CH{channel_id} has no interface configured")
    print(interface)
    break
else:
    raise SystemExit(f"CH{channel_id} is not present in {sys.argv[1]}")
PY
)" || fail "Unable to validate channel configuration."

[[ "$INTERFACE" != "mock" ]] || fail "CH$CHANNEL uses MockInterface. Hardware test was NOT run. Configure a validated hardware interface first."

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
PROGRAM_JSON="$TMP_DIR/program.json"
VERIFY_JSON="$TMP_DIR/verify.json"
READ_JSON="$TMP_DIR/read.json"
READ_MAP="$TMP_DIR/readback-map.json"

"$PYTHON_BIN" - "$READ_MAP" "$FIRMWARE_SIZE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
length = int(sys.argv[2])
path.write_text(
    json.dumps({"sections": [{"name": "firmware", "address": 0, "length": length}]}, indent=2) + "\n",
    encoding="utf-8",
)
PY

printf 'Plasma Hardware-in-the-Loop test\n'
printf '  Channel:   CH%s\n' "$CHANNEL"
printf '  Interface: %s\n' "$INTERFACE"
printf '  Firmware:  %s\n' "$FIRMWARE"
printf '  Size:      %s bytes\n' "$FIRMWARE_SIZE"
printf '  Server:    %s:%s\n' "$HOST" "$PORT"
printf '\nChecking server/channel status...\n'
"$PLASMA_BIN" --host "$HOST" --port "$PORT" status --channel "$CHANNEL" >/dev/null

assert_success() {
  local file="$1"
  local label="$2"
  "$PYTHON_BIN" - "$file" "$label" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
label = sys.argv[2]
result = payload.get("result") or {}
state = result.get("state")
if payload.get("ok") is not True or state != "success":
    raise SystemExit(f"{label} did not succeed: state={state!r}, payload={payload!r}")
print(f"{label}: PASS  job={result.get('job_id')}  elapsed_ms={result.get('elapsed_ms')}")
PY
}

printf '\nProgramming (server workflow: erase -> program -> verify)...\n'
"$PLASMA_BIN" --host "$HOST" --port "$PORT" program \
  --channel "$CHANNEL" \
  --bin "$FIRMWARE" \
  --timeout "$TIMEOUT_S" \
  --retries 0 \
  --no-progress >"$PROGRAM_JSON"
assert_success "$PROGRAM_JSON" "program"

printf '\nRunning an explicit second verify...\n'
"$PLASMA_BIN" --host "$HOST" --port "$PORT" verify \
  --channel "$CHANNEL" \
  --bin "$FIRMWARE" \
  --timeout "$TIMEOUT_S" \
  --retries 0 \
  --no-progress >"$VERIFY_JSON"
assert_success "$VERIFY_JSON" "verify"

printf '\nReading back the programmed byte range...\n'
"$PLASMA_BIN" --host "$HOST" --port "$PORT" read \
  --channel "$CHANNEL" \
  --map "$READ_MAP" \
  --timeout "$TIMEOUT_S" \
  --retries 0 \
  --no-progress >"$READ_JSON"
assert_success "$READ_JSON" "read-back"

READBACK_PATH="$($PYTHON_BIN - "$READ_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
files = (payload.get("result") or {}).get("output_files") or []
if len(files) != 1:
    raise SystemExit(f"expected exactly one read-back file, got: {files!r}")
print(files[0])
PY
)" || fail "Unable to locate read-back output file."

if [[ ! -f "$READBACK_PATH" && -f "$PYTHON_DIR/$READBACK_PATH" ]]; then
  READBACK_PATH="$PYTHON_DIR/$READBACK_PATH"
elif [[ ! -f "$READBACK_PATH" && -f "$ROOT_DIR/$READBACK_PATH" ]]; then
  READBACK_PATH="$ROOT_DIR/$READBACK_PATH"
fi
[[ -f "$READBACK_PATH" ]] || fail "Read-back file does not exist on this host: $READBACK_PATH"

printf '\nComparing read-back bytes with firmware...\n'
if ! cmp -s "$FIRMWARE" "$READBACK_PATH"; then
  printf 'Firmware SHA-256:  ' >&2
  sha256sum "$FIRMWARE" >&2 || true
  printf 'Read-back SHA-256: ' >&2
  sha256sum "$READBACK_PATH" >&2 || true
  fail "Read-back data differs from the firmware. Hardware test FAILED."
fi

FIRMWARE_SHA="$($PYTHON_BIN -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$FIRMWARE")"

printf '\n==> HARDWARE PASS\n'
printf 'CH%s %s bytes programmed, verified, read back, and matched byte-for-byte.\n' "$CHANNEL" "$FIRMWARE_SIZE"
printf 'SHA-256: %s\n' "$FIRMWARE_SHA"
printf 'Read-back: %s\n' "$READBACK_PATH"

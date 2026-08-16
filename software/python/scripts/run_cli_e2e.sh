#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_dir="$(mktemp -d)"
server_pid=""

cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -rf "$test_dir"
}
trap cleanup EXIT

cd "$project_dir"
python3 -c "from pathlib import Path; Path('$test_dir/firmware.bin').write_bytes(bytes(range(256)))"

python3 -m plasma_server.server --config config/plasma.yaml >"$test_dir/server.log" 2>&1 &
server_pid="$!"

ready=0
for _attempt in $(seq 1 50); do
  if python3 -m plasma_client.cli status >"$test_dir/status.json" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.05
done

if [[ "$ready" -ne 1 ]]; then
  sed -n '1,160p' "$test_dir/server.log" >&2
  exit 1
fi

python3 -m plasma_client.cli program \
  --channel 0 \
  --bin "$test_dir/firmware.bin" \
  --map config/map.example.json \
  --timeout 15 \
  --retries 1 >"$test_dir/program.json" 2>"$test_dir/program-progress.log"

python3 -m plasma_client.cli read \
  --channel 0 \
  --map config/map.example.json \
  --timeout 5 \
  --no-progress >"$test_dir/read.json"

python3 - "$test_dir/status.json" "$test_dir/program.json" "$test_dir/read.json" "$test_dir/program-progress.log" <<'PY'
import json
import sys
from pathlib import Path

status, program, read = [json.loads(Path(path).read_text(encoding="utf-8")) for path in sys.argv[1:4]]
progress = Path(sys.argv[4]).read_text(encoding="utf-8")
assert status["ok"] is True
assert len(status["channels"]) == 8
assert program["result"]["state"] == "success"
assert read["result"]["state"] == "success"
assert len(read["result"]["output_files"]) == 2
assert "PROGRAM" in progress
assert "ERASE" not in progress
assert "VERIFY" not in progress
assert "100.0%" in progress
print("CLI E2E: status/progress/program/read passed")
PY

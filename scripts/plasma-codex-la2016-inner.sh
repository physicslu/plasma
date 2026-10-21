#!/usr/bin/env bash
# Separate tmux; public status only, no raw USB or Codex stdout/stderr.
set -uo pipefail
umask 077
out="${PLASMA_LA2016_OUT:?}"
test "$(id -un)" = plasma-codex || exit 90
test "${RUNNER_NAME:-}" = SWPC-plasma-codex || exit 91
echo "PLASMA Codex -> guarded KINGST LA2016 loopback"
echo "Model must authorize fixed capability JSON; USB hidden from agent."
set +e
timeout --signal=TERM --kill-after=7s 245s \
  python3 scripts/plasma-codex-la2016.py --run
rc=$?
set -e
printf '%s\n' "$rc" > "$out/exit_code"
( cd "$out" && sha256sum exit_code > SHA256SUMS )
if test -f "$out/report.json"; then
  ( cd "$out" && sha256sum report.json >> SHA256SUMS )
fi
for file in "$out/"*hz-edges.csv; do
  if test -f "$file"; then
    ( cd "$out" && sha256sum "$(basename "$file")" >> SHA256SUMS )
  fi
done
touch "$out/complete"
echo "LA2016 job done; rc=$rc; no raw device/credential output"
sleep 40

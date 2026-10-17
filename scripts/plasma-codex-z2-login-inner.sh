#!/usr/bin/env bash
# No terminal contents from Z2 are copied to GitHub logs.
set -euo pipefail
umask 077
out="${PLASMA_Z2_LOGIN_OUT:?}"
test "$(id -un)" = plasma-codex
test "$RUNNER_NAME" = SWPC-plasma-codex
echo "PLASMA Z2 — dedicated Codex SSH/UART login smoke"
echo "Only sanitized stage status is displayed; no credentials/hosts/serial data."
echo "Starting fixed, limited read-only Z2 login checks."
set +e
timeout --signal=TERM --kill-after=5s 125s \
  python3 scripts/plasma-codex-z2-login.py --run
rc=$?
set -e
printf '%s\n' "$rc" > "$out/exit_code"
( cd "$out" && sha256sum exit_code > SHA256SUMS )
if test -f "$out/report.json"; then
  ( cd "$out" && sha256sum report.json >> SHA256SUMS )
fi
touch "$out/complete"
echo "Z2 login job finished: exit=$rc. Actions will keep read-only tmux monitor briefly."
sleep 50

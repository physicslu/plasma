#!/usr/bin/env bash
# Issue 981: owner-only bounded LA2016 Codex intent / supervised waveform test.
set -euo pipefail
umask 007
test "$(hostname)" = SWPC
test "$(id -un)" = plasma-codex
test "$(id -u)" -ne 0
test "${RUNNER_NAME:-}" = SWPC-plasma-codex
test "${GITHUB_REPOSITORY:-}" = physicslu/plasma
test "${GITHUB_EVENT_NAME:-}" = issue_comment
test "${GITHUB_REF:-}" = refs/heads/main
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]]
test "$(stat -c '%U:%G:%a' /run/plasma-codex)" = plasma-codex:plasma-monitor:2770
socket="/run/plasma-codex/la2016-${GITHUB_RUN_ID}.sock"
session="plasma-la2016-${GITHUB_RUN_ID}"
out="${RUNNER_TEMP:?}/plasma-la2016-${GITHUB_RUN_ID}"
test ! -e "$socket"
mkdir -m 0700 "$out"
export PLASMA_LA2016_OUT="$out"
cleanup() {
  tmux -S "$socket" kill-server >/dev/null 2>&1 || true
  rm -f "$socket"
}
trap cleanup EXIT INT TERM
echo "Codex intent -> bounded KINGST PWM1/CH0; run ${GITHUB_RUN_ID}"
echo "SWPC tmux observer:"
echo "tmux -S $socket attach-session -r -t $session"
tmux -S "$socket" -f /dev/null new-session -d -s "$session" \
  "bash scripts/plasma-codex-la2016-inner.sh"
for _ in {1..30}; do
  test -S "$socket" && break
  sleep 0.1
done
test -S "$socket"
chmod 0660 "$socket"
waited=0
while ((waited < 270)); do
  if test -f "$out/complete"; then
    code="$(cat "$out/exit_code")"
    [[ "$code" =~ ^[0-9]{1,3}$ ]] || exit 2
    (cd "$out" && sha256sum -c SHA256SUMS)
    echo "LA2016 Codex-agent job exit=$code; evidence sanitized"
    echo "tmux remains attached for 30 seconds"
    sleep 30
    exit "$code"
  fi
  if ! tmux -S "$socket" has-session -t "$session" 2>/dev/null; then
    echo "Codex tmux ended without completed report" >&2
    exit 2
  fi
  sleep 1
  waited=$((waited+1))
done
echo "LA2016 job exceeded host deadline; watchdog handles PWM OFF" >&2
exit 124

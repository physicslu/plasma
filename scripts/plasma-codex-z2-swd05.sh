#!/usr/bin/env bash
# Dedicated SWPC worker — bounded real Z2 SSH-based SWD-05 internal loopback, monitored via tmux.
set -euo pipefail
umask 007
test "$(hostname)" = SWPC
test "$(id -un)" = plasma-codex
test "$RUNNER_NAME" = SWPC-plasma-codex
test "$GITHUB_REPOSITORY" = physicslu/plasma
test "$GITHUB_REF" = refs/heads/main
test "$GITHUB_EVENT_NAME" = issue_comment
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]]
test -d /run/plasma-codex
test "$(stat -c '%U:%G:%a' /run/plasma-codex)" = plasma-codex:plasma-monitor:2770
socket="/run/plasma-codex/z2-swd05-${GITHUB_RUN_ID}.sock"
session="plasma-z2-swd05-${GITHUB_RUN_ID}"
out="${RUNNER_TEMP:?}/plasma-z2-swd05-${GITHUB_RUN_ID}"
test ! -e "$socket"
mkdir -m 0700 "$out"
export PLASMA_SWD05_OUT="$out"
cleanup() {
  tmux -S "$socket" kill-server >/dev/null 2>&1 || true
  rm -f "$socket"
}
trap cleanup EXIT INT TERM
echo "Fixed Z2 SSH-based SWD-05 internal loopback test, no power/reset/flash; run ${GITHUB_RUN_ID}"
echo "SWPC read-only live monitor:"
echo "tmux -S $socket attach-session -r -t $session"
tmux -S "$socket" -f /dev/null new-session -d -s "$session" \
  "bash scripts/plasma-codex-z2-swd05-inner.sh"
for _ in {1..30}; do
  test -S "$socket" && break
  sleep 0.1
done
test -S "$socket"
chmod 0660 "$socket"

waited=0
while ((waited < 165)); do
  if test -f "$out/complete"; then
    rc="$(cat "$out/exit_code")"
    [[ "$rc" =~ ^[0-9]{1,3}$ ]] || exit 2
    (cd "$out" && sha256sum -c SHA256SUMS)
    echo "Z2 SSH SWD-05 one-shot exit=$rc; evidence sanitized"
    echo "Read-only monitor will remain attachable for 40 seconds"
    sleep 40
    exit "$rc"
  fi
  if ! tmux -S "$socket" has-session -t "$session" 2>/dev/null; then
    echo "Z2 tmux session ended without report" >&2
    exit 2
  fi
  sleep 1
  waited=$((waited+1))
done
echo "Z2 SWD05 one-shot timed out" >&2
exit 124

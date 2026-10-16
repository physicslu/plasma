#!/usr/bin/env bash
# Issue #981 bootstrap: live, bounded tmux; never run this with elevated privileges.
set -euo pipefail
umask 007

test "$(id -un)" = plasma-codex
test "$GITHUB_REPOSITORY" = physicslu/plasma
test "$GITHUB_REF" = refs/heads/main
test "$GITHUB_EVENT_NAME" = issue_comment
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]]
test -n "${GITHUB_WORKSPACE:-}"
test -n "${RUNNER_TEMP:-}"
test -d /run/plasma-codex
test -w /run/plasma-codex

session="plasma-codex-${GITHUB_RUN_ID}"
socket="/run/plasma-codex/pilot-${GITHUB_RUN_ID}.sock"
out="${RUNNER_TEMP}/plasma-codex-981-${GITHUB_RUN_ID}"
test ! -e "$socket"
mkdir -m 0770 -p "$out"
export PLASMA_CODEX_PILOT_OUT="$out"

cleanup() {
  tmux -S "$socket" kill-server >/dev/null 2>&1 || true
  rm -f "$socket"
}
trap cleanup EXIT INT TERM

echo "Starting monitored Codex job; issue #981, GitHub run $GITHUB_RUN_ID"
echo "SSH read-only monitor: tmux -S $socket attach-session -r -t $session"
echo "Alternative log monitor: tail -f $out/codex.jsonl"

# Creates its own server/socket; the session is disposable after this Actions job.
tmux -S "$socket" -f /dev/null new-session -d -s "$session" \
  "bash scripts/plasma-codex-pilot-inner.sh"
for _ in {1..20}; do
  test -S "$socket" && break
  sleep 0.1
done
test -S "$socket"
chmod 0660 "$socket"

# CI waits on a real exit code, not on successful tmux creation. The inner
# process has its own timeout so loss of Actions cannot leave Codex infinite.
elapsed=0
while test "$elapsed" -lt 960; do
  if test -f "$out/exit_code"; then
    rc="$(cat "$out/exit_code")"
    [[ "$rc" =~ ^[0-9]{1,3}$ ]] || { echo "Malformed Codex exit code" >&2; exit 1; }
    echo "Codex actual exit code: $rc"
    if test -f "$out/SHA256SUMS"; then
      ( cd "$out" && sha256sum -c SHA256SUMS )
    else
      echo "Missing SHA256 manifest" >&2
      exit 1
    fi
    exit "$rc"
  fi
  if ! tmux -S "$socket" has-session -t "$session" 2>/dev/null; then
    echo "Codex tmux session exited without completion evidence" >&2
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed + 2))
  if (( elapsed % 30 == 0 )); then
    echo "Codex still active: ${elapsed}s; monitor session $session"
  fi
done
echo "Timed out waiting for bounded Codex session" >&2
exit 124

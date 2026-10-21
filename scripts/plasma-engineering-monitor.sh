#!/usr/bin/env bash
# Owner's SSH-only observer. Does not launch, authorize, or control any job.
set -euo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
viewer="$repo/scripts/plasma_engineering_monitor.py"
session="plasma-monitor"

command -v tmux >/dev/null
command -v python3 >/dev/null
command -v sg >/dev/null
test -f "$viewer"

# A long-running tmux server retains the supplementary groups it had when
# started. Query the operator's CURRENT NSS membership, not the old server's
# group list. Refuse to start viewers if switching to the monitor group is not
# authorized; do not prompt for a group password or widen file permissions.
group="plasma-monitor"
if ! getent group "$group" >/dev/null ||
   ! id -nG "$(id -un)" | tr ' ' '\n' | grep -Fxq "$group"; then
  echo "MONITOR_GROUP_UNAVAILABLE: $group is not an operator group" >&2
  exit 1
fi

# Each viewer switches group INSIDE its tmux pane, even if the tmux server was
# created before the operator joined plasma-monitor.
viewer_command() {
  local inner
  printf -v inner 'exec python3 -u %q view %s' "$viewer" "$1"
  printf 'sg %q -c %q' "$group" "$inner"
}

# Owned by the logged-in operator. No cross-user tmux control socket is needed.
# Address the named window, not :0: the operator's base-index can be 1.
window="$session:overview"
if ! tmux has-session -t "=$session" 2>/dev/null; then
  left="$(viewer_command path2)"
  tmux new-session -d -s "$session" -n overview -c "$repo" "$left"
fi

# Repair a preexisting one-pane session left behind by the old :0 bug.
panes="$(tmux list-panes -t "$window" -F '#{pane_id}' | wc -l)"
if [ "$panes" -eq 1 ]; then
  right="$(viewer_command path3)"
  tmux split-window -d -h -t "$window" -c "$repo" "$right"
elif [ "$panes" -ne 2 ]; then
  echo "MONITOR_UNEXPECTED_PANE_COUNT: $panes" >&2
  exit 1
fi

tmux select-layout -t "$window" even-horizontal
exec tmux attach-session -t "=$session"

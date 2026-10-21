#!/usr/bin/env bash
# Owner's SSH-only observer. Does not launch, authorize, or control any job.
set -euo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
viewer="$repo/scripts/plasma_engineering_monitor.py"
session="plasma-monitor"

command -v tmux >/dev/null
command -v python3 >/dev/null
test -f "$viewer"

# Owned by the logged-in operator. No cross-user tmux control socket is needed.
# Address the named window, not :0: the operator's base-index can be 1.
window="$session:overview"
if ! tmux has-session -t "=$session" 2>/dev/null; then
  printf -v left 'python3 -u %q view path2' "$viewer"
  tmux new-session -d -s "$session" -n overview -c "$repo" "$left"
fi

# Repair a preexisting one-pane session left behind by the old :0 bug.
panes="$(tmux list-panes -t "$window" -F '#{pane_id}' | wc -l)"
if [ "$panes" -eq 1 ]; then
  printf -v right 'python3 -u %q view path3' "$viewer"
  tmux split-window -d -h -t "$window" -c "$repo" "$right"
elif [ "$panes" -ne 2 ]; then
  echo "MONITOR_UNEXPECTED_PANE_COUNT: $panes" >&2
  exit 1
fi

tmux select-layout -t "$window" even-horizontal
exec tmux attach-session -t "=$session"

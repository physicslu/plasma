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
if ! tmux has-session -t "=$session" 2>/dev/null; then
  printf -v left 'python3 -u %q view path2' "$viewer"
  printf -v right 'python3 -u %q view path3' "$viewer"
  tmux new-session -d -s "$session" -n overview -c "$repo" "$left"
  tmux split-window -d -h -t "=$session:0" -c "$repo" "$right"
  tmux select-layout -t "=$session:0" even-horizontal
fi

exec tmux attach-session -t "=$session"

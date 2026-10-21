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

# Owned by the logged-in operator. Never change global tmux settings or
# touch another session. Force 1/2 even when the operator's base-index is 0.
# Retain existing viewers and their monitor state when migrating overview.
if ! tmux has-session -t "=$session" 2>/dev/null; then
  left="$(viewer_command path2)"
  tmux new-session -d -s "$session" -n path2 -c "$repo" "$left"
fi

windows="$(tmux list-windows -t "=$session" -F '#{window_name}' | paste -sd ' ' -)"
case "$windows" in
  overview)
    # Migrate legacy left/right layout without killing either viewer process.
    panes="$(tmux list-panes -t "$session:overview" -F '#{pane_id}' | wc -l)"
    if [ "$panes" -eq 2 ]; then
      right_pane="$(tmux list-panes -t "$session:overview" -F '#{pane_id}' | tail -n 1)"
      tmux break-pane -d -s "$right_pane" -t "$session:2" -n path3
    elif [ "$panes" -ne 1 ]; then
      echo "MONITOR_UNEXPECTED_PANE_COUNT: $panes" >&2
      exit 1
    fi
    tmux rename-window -t "$session:overview" path2
    ;;
  path2|path2\ path3)
    ;;
  *)
    echo "MONITOR_UNEXPECTED_WINDOWS: $windows" >&2
    exit 1
    ;;
esac

# Ensure Ctrl+A,1 and Ctrl+A,2 select the same logical paths regardless of
# tmux base-index. Never renumber or modify other tmux sessions.
path2_index="$(tmux display-message -p -t "$session:path2" '#{window_index}')"
if [ "$path2_index" != 1 ]; then
  tmux move-window -d -s "$session:path2" -t "$session:1"
fi
path2_panes="$(tmux list-panes -t "$session:1" -F '#{pane_id}' | wc -l)"
if [ "$path2_panes" -ne 1 ]; then
  echo "MONITOR_UNEXPECTED_PANE_COUNT: $path2_panes" >&2
  exit 1
fi

if ! tmux has-session -t "$session:path3" 2>/dev/null; then
  right="$(viewer_command path3)"
  tmux new-window -d -t "$session:2" -n path3 -c "$repo" "$right"
fi

path3_index="$(tmux display-message -p -t "$session:path3" '#{window_index}')"
path3_panes="$(tmux list-panes -t "$session:2" -F '#{pane_id}' | wc -l)"
if [ "$path3_index" != 2 ] || [ "$path3_panes" -ne 1 ]; then
  echo "MONITOR_UNEXPECTED_PATH3_LAYOUT: index=$path3_index panes=$path3_panes" >&2
  exit 1
fi

tmux select-window -t "$session:1"
exec tmux attach-session -t "=$session"

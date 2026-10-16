#!/usr/bin/env bash
# Called only by the dedicated SWPC runner's tmux pilot session.
set -uo pipefail
umask 077
out="${PLASMA_CODEX_PILOT_OUT:?missing output dir}"
test "$(id -un)" = plasma-codex || exit 90
test "$GITHUB_REPOSITORY" = physicslu/plasma || exit 91
cd "${GITHUB_WORKSPACE:?missing checkout}" || exit 92

cat > "$out/prompt.txt" <<'PROMPT'
PLASMA Issue #981 isolated Codex read-only bootstrap acceptance.
Read ONLY these PUBLIC checked-in source files under the current repository:
AGENTS.md, .github/workflows/plasma-codex-pilot.yml,
scripts/plasma-codex-pilot.sh, scripts/plasma-codex-pilot-inner.sh,
scripts/plasma-codex-pilot-contract.py,
docs/development/plasma-codex-pilot.md.
Return a concise technical assessment of the guard, tmux and evidence flow.
Do not edit any file, execute shell commands, access secret files, scan /proc,
/dev, /run or the network, contact Z2, USB Hub, LA or external devices.
Do not invoke any tools beyond reading the listed public files.
Do not claim any hardware test, PR, deployment, or runner isolation test passed.
PROMPT

date -u '+start_utc=%Y-%m-%dT%H:%M:%SZ' > "$out/metadata.txt"
printf 'github_run_id=%s\nsource_sha=%s\n' \
  "$GITHUB_RUN_ID" "$(git rev-parse HEAD)" >> "$out/metadata.txt"

set +e
timeout --signal=TERM --kill-after=10s 900s \
  codex exec \
    --json \
    --sandbox read-only \
    --ask-for-approval never \
    --output-last-message "$out/last-message.txt" \
    - < "$out/prompt.txt" 2>&1 | tee "$out/codex.jsonl"
rc="${PIPESTATUS[0]}"
set -e
printf 'end_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$out/metadata.txt"
printf '%s\n' "$rc" > "$out/exit_code.pending"
mv "$out/exit_code.pending" "$out/exit_code"
( cd "$out" && sha256sum exit_code metadata.txt > SHA256SUMS )
printf '\nCodex ended with rc=%s. Terminal session available until Actions finalizes.\n' "$rc"

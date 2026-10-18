#!/usr/bin/env bash
# Called only by the dedicated SWPC runner's tmux pilot session.
set -uo pipefail
umask 077
out="${PLASMA_CODEX_PILOT_OUT:?missing output dir}"
test "$(id -un)" = plasma-codex || exit 90
test "$GITHUB_REPOSITORY" = physicslu/plasma || exit 91
cd "${GITHUB_WORKSPACE:?missing checkout}" || exit 92

# A deterministic runner-owned preparer embeds ONLY six checked-in public files
# in the prompt. The model is not asked to discover paths or invoke any tools.
python3 scripts/plasma-codex-pilot-acceptance.py prepare \
  --root "${GITHUB_WORKSPACE}" --out "$out" || exit 93

date -u '+start_utc=%Y-%m-%dT%H:%M:%SZ' > "$out/metadata.txt"
printf 'github_run_id=%s\nsource_sha=%s\n' \
  "$GITHUB_RUN_ID" "$(git rev-parse HEAD)" >> "$out/metadata.txt"

set +e
timeout --signal=TERM --kill-after=10s 900s \
  codex --ask-for-approval never exec \
    --json \
    --sandbox read-only \
    --output-last-message "$out/last-message.txt" \
    - < "$out/prompt.txt" 2>&1 | tee "$out/codex.jsonl"
rc="${PIPESTATUS[0]}"
set -e
# A successful Codex process is not accepted unless it returned trace-clean,
# schema-valid guard/tmux/evidence findings grounded in supplied source bytes.
if python3 scripts/plasma-codex-pilot-acceptance.py verify \
  --root "${GITHUB_WORKSPACE}" --out "$out" --codex-exit "$rc"; then
  final_rc=0
else
  final_rc=1
fi
printf 'end_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$out/metadata.txt"
printf '%s\n' "$final_rc" > "$out/exit_code"
( cd "$out" && \
  if test -f assessment.json; then
    sha256sum exit_code metadata.txt input-manifest.json acceptance-report.json assessment.json > SHA256SUMS
  else
    sha256sum exit_code metadata.txt input-manifest.json acceptance-report.json > SHA256SUMS
  fi )
touch "$out/complete"
printf '\nCodex rc=%s; verified pilot rc=%s. This is not hardware acceptance.\n' "$rc" "$final_rc"


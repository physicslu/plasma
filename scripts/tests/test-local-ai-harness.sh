#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
helper="$repo/scripts/local-ai-harness"
temporary="$(mktemp -d)"
sleep_pid=""
cleanup() {
  if [[ -n "$sleep_pid" ]] && kill -0 "$sleep_pid" 2>/dev/null; then
    kill "$sleep_pid"
    wait "$sleep_pid" 2>/dev/null || true
  fi
  rm -rf "$temporary"
}
trap cleanup EXIT
fake_bin="$temporary/bin"
fake_log="$temporary/calls.log"
mkdir -p "$fake_bin"

fail() {
  printf '[local-ai-test] FAIL: %s\n' "$*" >&2
  exit 1
}

help_output="$("$helper" --help)"
grep -Fq 'scripts/local-ai-harness <command>' <<<"$help_output" || fail 'help lacks usage'
grep -Fq 'PLASMA_LOCAL_AI_MODEL' <<<"$help_output" || fail 'help lacks model override'

status_output="$(cd "$temporary" && PATH=/usr/bin:/bin PLASMA_HARNESS_PORT=3099 "$helper" status)"
grep -Fq "Plasma repository: $repo" <<<"$status_output" || fail 'repository root detection failed'
grep -Fq 'Model: qwen3.8:27b-mlx' <<<"$status_output" || fail 'default model missing'
grep -Fq 'Harness Web port: 3099' <<<"$status_output" || fail 'port override missing'
grep -Fq 'OLLAMA_KEEP_ALIVE=-1' <<<"$status_output" || fail 'runtime policy missing'

if PLASMA_HARNESS_PORT=invalid "$helper" status >/dev/null 2>&1; then
  fail 'invalid Harness port was accepted'
fi
if PLASMA_OLLAMA_URL=https://example.invalid:11434 "$helper" status >/dev/null 2>&1; then
  fail 'non-local Ollama URL was accepted'
fi
if PLASMA_OLLAMA_URL=http://127.0.0.1:65536 "$helper" status >/dev/null 2>&1; then
  fail 'out-of-range Ollama port was accepted'
fi

cat >"$fake_bin/curl" <<'EOF'
#!/usr/bin/env bash
case "${*: -1}" in
  */api/tags)
    if [[ "${FAKE_MODEL_PRESENT:-0}" == 1 ]]; then
      printf '{"models":[{"name":"%s"}]}\n' "${FAKE_MODEL:-qwen3.8:27b-mlx}"
    else
      printf '{"models":[]}\n'
    fi
    ;;
  */api/generate)
    case "${FAKE_CURL_MODE:-normal}" in
      normal) printf '{"model":"%s","response":"OK","done":true}\n' "${FAKE_MODEL:-qwen3.8:27b-mlx}" ;;
      reasoning) printf '{"model":"%s","thinking":"reasoning tokens","response":"","done":true}\n' "${FAKE_MODEL:-qwen3.8:27b-mlx}" ;;
      non_ok) printf '{"model":"%s","response":"Ready","done":true}\n' "${FAKE_MODEL:-qwen3.8:27b-mlx}" ;;
      malformed) printf '{not-json\n' ;;
      http_failure) exit 22 ;;
      empty) printf '{"model":"%s","response":"","thinking":"","done":true}\n' "${FAKE_MODEL:-qwen3.8:27b-mlx}" ;;
      wrong_model) printf '{"model":"different-model","response":"Ready","done":true}\n' ;;
      incomplete) printf '{"model":"%s","response":"partial","done":false}\n' "${FAKE_MODEL:-qwen3.8:27b-mlx}" ;;
      invalid_type) printf '{"model":"%s","response":[],"done":true}\n' "${FAKE_MODEL:-qwen3.8:27b-mlx}" ;;
      *) exit 64 ;;
    esac
    ;;
  *) exit 22 ;;
esac
EOF

cat >"$fake_bin/ollama" <<'EOF'
#!/usr/bin/env bash
printf 'ollama|%s|%s|%s|%s|%s\n' "$PWD" "$*" "$OLLAMA_LOAD_TIMEOUT" "$OLLAMA_KEEP_ALIVE" "$OLLAMA_NUM_PARALLEL" >>"$FAKE_LOG"
EOF

cat >"$fake_bin/dsh" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  printf 'test-version\n'
  exit 0
fi
printf 'dsh|%s|%s\n' "$PWD" "$*" >>"$FAKE_LOG"
EOF
chmod +x "$fake_bin/curl" "$fake_bin/ollama" "$fake_bin/dsh"

missing_output="$(PATH="$fake_bin:/usr/bin:/bin" FAKE_MODEL_PRESENT=0 \
  PLASMA_LOCAL_AI_MODEL=missing-model "$helper" warmup 2>&1 || true)"
grep -Fq 'Model missing-model is not installed' <<<"$missing_output" || fail 'missing model error is unclear'
grep -Fq 'will not pull it automatically' <<<"$missing_output" || fail 'missing model error lacks no-pull policy'
[[ ! -s "$fake_log" ]] || fail 'missing-model warmup invoked Ollama or Harness'

assert_warmup_success() {
  local mode="$1"
  PATH="$fake_bin:/usr/bin:/bin" FAKE_MODEL_PRESENT=1 FAKE_MODEL=test-model FAKE_CURL_MODE="$mode" \
    PLASMA_LOCAL_AI_MODEL=test-model "$helper" warmup >/dev/null || fail "warmup rejected successful $mode response"
}

assert_warmup_failure() {
  local mode="$1" output
  if output="$(PATH="$fake_bin:/usr/bin:/bin" FAKE_MODEL_PRESENT=1 FAKE_MODEL=test-model FAKE_CURL_MODE="$mode" \
    PLASMA_LOCAL_AI_MODEL=test-model "$helper" warmup 2>&1)"; then
    fail "warmup accepted invalid $mode response"
  fi
  grep -Eq 'warmup request failed|invalid warmup completion' <<<"$output" || \
    fail "warmup $mode failure was unclear"
}

assert_warmup_success normal
assert_warmup_success reasoning
assert_warmup_success non_ok
assert_warmup_failure malformed
assert_warmup_failure http_failure
assert_warmup_failure empty
assert_warmup_failure wrong_model
assert_warmup_failure incomplete
assert_warmup_failure invalid_type

PATH="$fake_bin:/usr/bin:/bin" FAKE_LOG="$fake_log" TMPDIR="$temporary" \
  PLASMA_OLLAMA_URL=http://localhost:12345 "$helper" ollama >/dev/null
grep -Fq "ollama|$repo|serve|30m|-1|1" "$fake_log" || fail 'Ollama foreground policy or repository detection mismatch'

(cd "$temporary" && PATH="$fake_bin:/usr/bin:/bin" FAKE_LOG="$fake_log" TMPDIR="$temporary" \
  PLASMA_HARNESS_PORT=3099 "$helper" harness >/dev/null)
grep -Fq "dsh|$repo|--profile web --port 3099" "$fake_log" || fail 'Harness cwd or arguments mismatch'

sleep 30 &
sleep_pid=$!
ownership_dir="$temporary/plasma-local-ai-${UID:-$(id -u)}"
mkdir -p "$ownership_dir"
printf '%s\n' "$sleep_pid" >"$ownership_dir/ollama.pid"
printf '%s\n' "$sleep_pid" >"$ownership_dir/harness.pid"
if TMPDIR="$temporary" "$helper" stop >/dev/null 2>&1; then
  fail 'stop accepted ownership records for an unrelated process'
fi
kill -0 "$sleep_pid" 2>/dev/null || fail 'stop killed an unrelated process'
kill "$sleep_pid"
wait "$sleep_pid" 2>/dev/null || true
sleep_pid=""

printf '[local-ai-test] Launcher regression checks passed.\n'

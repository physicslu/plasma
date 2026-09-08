#!/usr/bin/env bash
set -Eeuo pipefail

script_path="${BASH_SOURCE[0]}"
while [[ -L "$script_path" ]]; do
  script_dir="$(cd -P "$(dirname "$script_path")" && pwd)"
  script_path="$(readlink "$script_path")"
  [[ "$script_path" == /* ]] || script_path="$script_dir/$script_path"
done
repo_root="$(cd -P "$(dirname "$script_path")/.." && pwd)"
bench_dir="$repo_root/data/ic-support/benchmarks/nxp-kl25"

bench_root="${PLASMA_KL25_BENCH_ROOT:-/storage/projects/plasma-benchmark/nxp-kl25}"
source_dir="$bench_root/source"
pre_ai_dir="$bench_root/pre-ai"
runs_dir="$bench_root/runs"
legacy_run_dir="$bench_root/qwen-live"
ollama_url="${PLASMA_OLLAMA_URL:-http://127.0.0.1:11434}"

usage() {
  cat <<'EOF'
Usage: bash scripts/ic-support-kl25-live.sh <command> [argument]

Commands:
  status               Validate pre-AI, frozen runtime envelope, and loopback Ollama/model identity.
  context-audit        Measure deterministic cross-pack context compaction without model inference.
  build                Rebuild the deterministic Gate-3 pre-AI workspace from locked PDFs.
  run                  Execute one new frozen live qualification run in a unique run directory.
  diagnose [run-dir]   Diagnose one retained run without modifying its raw response.
  help                 Show this help.

Default SWPC benchmark layout:
  /storage/projects/plasma-benchmark/nxp-kl25/source
  /storage/projects/plasma-benchmark/nxp-kl25/pre-ai
  /storage/projects/plasma-benchmark/nxp-kl25/runs/<UTC-run-id>

Environment overrides:
  PLASMA_KL25_BENCH_ROOT   Benchmark root directory.
  PLASMA_OLLAMA_URL        Loopback Ollama URL; default http://127.0.0.1:11434.

The supported topology keeps source/evidence/run artifacts on SWPC. The SWPC
loopback Ollama endpoint may be backed by the established SSH reverse tunnel to
the Mac model host. Direct LAN Ollama URLs are not accepted by the qualification harness.
EOF
}

fail() {
  printf '[kl25-live] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

validate_loopback_url() {
  [[ "$ollama_url" =~ ^http://(127\.0\.0\.1|localhost|\[::1\]):[0-9]+/?$ ]] || \
    fail "PLASMA_OLLAMA_URL must be an HTTP loopback URL"
  ollama_url="${ollama_url%/}"
}

contract_model() {
  python3 - "$bench_dir/live-model-qualification-contract.json" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["live_runtime"]["model_id"])
PY
}

print_contract_runtime() {
  python3 - "$bench_dir/live-model-qualification-contract.json" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
runtime = value["live_runtime"]
generation = runtime["generation"]
context = runtime["context_protocol"]
print(f"[kl25-live] qualification_contract: {value['contract_id']}")
print(f"[kl25-live] context_strategy: {context['strategy']}")
print(f"[kl25-live] num_ctx: {generation['num_ctx']}")
print(f"[kl25-live] max_tokens: {generation['max_tokens']}")
PY
}

validate_pre_ai_workspace() {
  python3 - "$bench_dir" "$pre_ai_dir" <<'PY'
import json
import sys
from pathlib import Path

bench_dir = Path(sys.argv[1])
pre_ai_dir = Path(sys.argv[2])
sys.path.insert(0, str(bench_dir))

import run_ollama_semantic

manifest, packs, _, _ = run_ollama_semantic.load_pre_ai_workspace(pre_ai_dir)
contract = json.loads((bench_dir / "live-model-qualification-contract.json").read_text(encoding="utf-8"))
required = contract["required_input"]

checks = {
    "target": manifest.get("target") == contract.get("target"),
    "bundle_digest": manifest.get("bundle_digest") == required.get("bundle_digest"),
    "pre_ai_manifest_digest": manifest.get("manifest_digest") == required.get("pre_ai_manifest_digest"),
    "pack_count": len(packs) == 8,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("pre-AI qualification binding mismatch: " + ", ".join(failed))

print("[kl25-live] pre-AI workspace: PASS")
print(f"[kl25-live] target: {manifest['target']}")
print(f"[kl25-live] bundle_digest: {manifest['bundle_digest']}")
print(f"[kl25-live] manifest_digest: {manifest['manifest_digest']}")
print(f"[kl25-live] pack_count: {len(packs)}")
PY
}

validate_ollama_identity() {
  local model version_json tags_json
  model="$(contract_model)"
  version_json="$(curl --silent --show-error --fail --max-time 5 "$ollama_url/api/version")" || \
    fail "Ollama version endpoint is unavailable at $ollama_url; check the reverse tunnel"
  tags_json="$(curl --silent --show-error --fail --max-time 10 "$ollama_url/api/tags")" || \
    fail "Ollama tags endpoint is unavailable at $ollama_url; check the reverse tunnel"

  python3 - "$model" "$version_json" "$tags_json" <<'PY'
import json
import re
import sys

model_id, version_raw, tags_raw = sys.argv[1:]
version = json.loads(version_raw)
tags = json.loads(tags_raw)
ollama_version = version.get("version")
if not isinstance(ollama_version, str) or not ollama_version.strip():
    raise SystemExit("Ollama /api/version did not return a usable version")
models = tags.get("models")
if not isinstance(models, list):
    raise SystemExit("Ollama /api/tags models is not an array")
matches = [item for item in models if isinstance(item, dict) and item.get("name") == model_id]
if len(matches) != 1:
    raise SystemExit(f"expected exactly one installed model named {model_id}; found {len(matches)}")
digest = matches[0].get("digest")
if not isinstance(digest, str) or re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", digest) is None:
    raise SystemExit("installed model digest is missing or malformed")
print("[kl25-live] Ollama loopback: PASS")
print(f"[kl25-live] Ollama version: {ollama_version}")
print(f"[kl25-live] model: {model_id}")
print(f"[kl25-live] model_digest: {digest}")
PY
}

run_status() {
  require_command python3
  require_command curl
  validate_loopback_url
  [[ -d "$pre_ai_dir" ]] || fail "pre-AI workspace missing: $pre_ai_dir"
  validate_pre_ai_workspace
  print_contract_runtime
  validate_ollama_identity
}

run_context_audit() {
  require_command python3
  [[ -d "$pre_ai_dir" ]] || fail "pre-AI workspace missing: $pre_ai_dir"
  validate_pre_ai_workspace
  python3 "$bench_dir/audit_semantic_context.py" --input-dir "$pre_ai_dir"
}

run_build() {
  require_command python3
  require_command pdftotext
  [[ -d "$source_dir" ]] || fail "source directory missing: $source_dir"
  [[ -f "$source_dir/KL25P80M48SF0.pdf" ]] || fail "locked KL25 data sheet missing"
  [[ -f "$source_dir/KL25P80M48SF0RM.pdf" ]] || fail "locked KL25 reference manual missing"

  mkdir -p "$bench_root"
  local tmp_dir="$bench_root/.pre-ai.tmp.$$"
  rm -rf "$tmp_dir"
  trap 'rm -rf "$tmp_dir"' EXIT

  python3 "$bench_dir/build_evidence_pack.py" \
    --source-dir "$source_dir" \
    --output-dir "$tmp_dir"

  rm -rf "$pre_ai_dir"
  mv "$tmp_dir" "$pre_ai_dir"
  trap - EXIT
  printf '[kl25-live] pre-AI workspace rebuilt atomically: %s\n' "$pre_ai_dir"
  validate_pre_ai_workspace
}

run_live() {
  run_status
  mkdir -p "$runs_dir"

  local run_id run_dir rc
  run_id="$(date -u +%Y%m%dT%H%M%SZ)"
  run_dir="$runs_dir/$run_id"
  if [[ -e "$run_dir" ]]; then
    run_id="$run_id-$$"
    run_dir="$runs_dir/$run_id"
  fi
  mkdir "$run_dir"

  printf '[kl25-live] run_dir: %s\n' "$run_dir"
  set +e
  python3 "$bench_dir/run_live_model_qualification.py" \
    --input-dir "$pre_ai_dir" \
    --output-dir "$run_dir" \
    --ollama-url "$ollama_url"
  rc=$?
  set -e

  ln -sfn "$run_id" "$runs_dir/latest"
  printf '[kl25-live] retained run: %s\n' "$run_dir"
  if (( rc != 0 )); then
    printf '[kl25-live] qualification did not reach READY_FOR_REVIEW; raw artifacts were preserved.\n' >&2
    printf '[kl25-live] diagnose with: bash scripts/ic-support-kl25-live.sh diagnose %q\n' "$run_dir" >&2
  fi
  return "$rc"
}

resolve_diagnostic_dir() {
  local requested="${1:-}"
  if [[ -n "$requested" ]]; then
    if [[ -f "$requested" ]]; then
      dirname "$requested"
    else
      printf '%s\n' "$requested"
    fi
    return
  fi
  if [[ -L "$runs_dir/latest" || -d "$runs_dir/latest" ]]; then
    printf '%s\n' "$runs_dir/latest"
    return
  fi
  if [[ -f "$legacy_run_dir/raw-response.txt" ]]; then
    printf '%s\n' "$legacy_run_dir"
    return
  fi
  fail "no retained run found; pass an explicit run directory"
}

run_diagnose() {
  require_command python3
  local run_dir
  run_dir="$(resolve_diagnostic_dir "${1:-}")"
  [[ -f "$run_dir/raw-response.txt" ]] || fail "raw-response.txt missing under $run_dir"

  python3 - "$bench_dir" "$pre_ai_dir" "$run_dir" <<'PY'
import json
import sys
from pathlib import Path

bench_dir = Path(sys.argv[1])
pre_ai_dir = Path(sys.argv[2])
run_dir = Path(sys.argv[3]).resolve()
raw_path = run_dir / "raw-response.txt"
raw = raw_path.read_text(encoding="utf-8")

print("===== KL25 LIVE RUN DIAGNOSIS =====")
print("run_dir    =", run_dir)
print("raw_bytes  =", len(raw.encode("utf-8")))
print("raw_chars  =", len(raw))
print("starts_{   =", raw.lstrip().startswith("{"))
print("ends_}     =", raw.rstrip().endswith("}"))
print("has_fence  =", "```" in raw)
print("has_think_marker =", "<think>" in raw or "</think>" in raw)

try:
    json.loads(raw)
except json.JSONDecodeError as exc:
    print("FULL_JSON   = FAIL")
    print("json_error  =", exc.msg)
    print("json_line   =", exc.lineno)
    print("json_column =", exc.colno)
    print("json_pos    =", exc.pos)
else:
    print("FULL_JSON   = PASS")

stripped = raw.lstrip()
leading = len(raw) - len(stripped)
decoder = json.JSONDecoder()
first_text = None
try:
    _, end = decoder.raw_decode(stripped)
except json.JSONDecodeError as exc:
    print("FIRST_DOCUMENT = FAIL")
    print("first_error =", exc.msg)
else:
    first_text = stripped[:end]
    trailing = stripped[end:]
    print("FIRST_DOCUMENT = PASS")
    print("first_document_chars =", len(first_text))
    print("leading_whitespace_chars =", leading)
    print("trailing_chars =", len(trailing))
    print("trailing_nonwhitespace =", bool(trailing.strip()))
    print("trailing_has_think_marker =", "<think>" in trailing or "</think>" in trailing)
    if trailing.strip():
        print("trailing_preview =", repr(trailing[:240]))

semantic_run_path = run_dir / "semantic-run.json"
if semantic_run_path.is_file():
    run = json.loads(semantic_run_path.read_text(encoding="utf-8"))
    print("semantic_status =", run.get("status"))
    error = run.get("error") if isinstance(run.get("error"), dict) else {}
    print("semantic_error_class =", error.get("class"))
    print("semantic_error_type =", error.get("type"))
    print("semantic_error_message =", error.get("message"))
    context = run.get("context") if isinstance(run.get("context"), dict) else {}
    print("context_strategy =", context.get("strategy"))
    print("context_page_occurrences =", context.get("page_occurrences"))
    print("context_unique_physical_pages =", context.get("unique_physical_pages"))
    print("context_duplicates_removed =", context.get("duplicate_occurrences_removed"))
    print("context_bytes =", context.get("context_bytes"))
    print("legacy_context_bytes =", context.get("legacy_context_bytes"))
    print("prompt_bytes =", run.get("prompt", {}).get("byte_length"))
    metadata = run.get("transport_metadata") if isinstance(run.get("transport_metadata"), dict) else {}
    print("provider_model =", metadata.get("response_model"))
    print("provider_done =", metadata.get("done"))
    print("provider_done_reason =", metadata.get("done_reason"))
    print("provider_usage =", metadata.get("usage"))

provenance_path = run_dir / "live-run-provenance.json"
if provenance_path.is_file():
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    execution = provenance.get("execution") if isinstance(provenance.get("execution"), dict) else {}
    generation = execution.get("generation") if isinstance(execution.get("generation"), dict) else {}
    print("requested_num_ctx =", generation.get("num_ctx"))
    print("requested_max_tokens =", generation.get("max_tokens"))

if first_text is not None and pre_ai_dir.is_dir():
    sys.path.insert(0, str(bench_dir))
    import run_ollama_semantic
    import semantic_extraction

    try:
        _, packs, _, contract = run_ollama_semantic.load_pre_ai_workspace(pre_ai_dir)
        semantic_extraction.parse_model_result(first_text, contract=contract, packs=packs)
    except Exception as exc:
        print("FIRST_DOCUMENT_SEMANTIC_CONTRACT = FAIL")
        print("first_document_semantic_error_type =", type(exc).__name__)
        print("first_document_semantic_error =", str(exc))
    else:
        print("FIRST_DOCUMENT_SEMANTIC_CONTRACT = PASS")

report_path = run_dir / "qualification-report.json"
if report_path.is_file():
    report = json.loads(report_path.read_text(encoding="utf-8"))
    print("qualification_status =", report.get("status"))
    integrity = report.get("integrity") if isinstance(report.get("integrity"), dict) else {}
    screening = report.get("semantic_screening") if isinstance(report.get("semantic_screening"), dict) else {}
    review = report.get("review") if isinstance(report.get("review"), dict) else {}
    print("integrity_status =", integrity.get("status"))
    print("integrity_errors =", integrity.get("errors"))
    print("semantic_screening_status =", screening.get("status"))
    print("semantic_screening_errors =", screening.get("errors"))
    print("review_status =", review.get("status"))
    print("review_errors =", review.get("errors"))
PY
}

main() {
  local command="${1:-help}"
  case "$command" in
    status)
      run_status
      ;;
    context-audit)
      run_context_audit
      ;;
    build)
      run_build
      ;;
    run)
      run_live
      ;;
    diagnose)
      run_diagnose "${2:-}"
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      usage >&2
      fail "Unknown command: $command"
      ;;
  esac
}

main "$@"
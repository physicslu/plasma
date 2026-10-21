#!/usr/bin/env bash
# GitHub-hosted only: execute immutable A1 ELF under isolated ARMv7 QEMU.
# NEVER invoke this wrapper on the persistent SWPC Docker daemon.
set -euo pipefail
test "$GITHUB_ACTIONS" = true
test "$RUNNER_ENVIRONMENT" = github-hosted
test "$GITHUB_REPOSITORY" = physicslu/plasma
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]]
test -n "$RUNNER_TEMP"
test -n "$GITHUB_WORKSPACE"
test -z "$(printenv SSH_AUTH_SOCK || true)"

readonly ARTIFACT_DIR="$RUNNER_TEMP/plasma-hil-a15-artifact"
readonly REPORT_DIR="$RUNNER_TEMP/plasma-hil-a15-report"
readonly ARM_IMAGE='arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c'
test -d "$ARTIFACT_DIR"
test ! -e "$REPORT_DIR"
umask 077
mkdir -m 700 "$REPORT_DIR"

python3 scripts/hil-a15-armv7-qemu.py verify --artifact-dir "$ARTIFACT_DIR"
timeout 120s docker run --rm --platform linux/arm/v7 \
  --network none --cap-drop=ALL --security-opt no-new-privileges \
  --read-only --pids-limit 64 --memory 256m \
  --tmpfs /tmp:rw,nosuid,nodev,size=16m \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$ARTIFACT_DIR,dst=/artifact,readonly" \
  --mount "type=bind,src=$GITHUB_WORKSPACE/scripts,dst=/probe,readonly" \
  --mount "type=bind,src=$REPORT_DIR,dst=/result" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$ARM_IMAGE" python3 /probe/hil-a15-armv7-qemu.py execute \
    --artifact-dir /artifact --report /result/qemu-execution.json \
    --repetitions 1000
test -s "$REPORT_DIR/qemu-execution.json"
python3 - "$REPORT_DIR/qemu-execution.json" <<'PY'
import json, pathlib, sys
r=json.loads(pathlib.Path(sys.argv[1]).read_text())
assert r['schema']=='plasma-hil-a15-armv7-qemu-runtime-v1'
assert r['status']==r['emu_execution']=='PASS'
assert r['calls']==1000
assert r['real_z2_a2']==r['mmio_uio']==r['fpga_dut']=='NOT_RUN'
assert r['m1']=='NO_GO'
print('PLASMA_HIL_A15_HOSTED_QEMU_RECEIPT_PASS')
PY
(cd "$REPORT_DIR" && sha256sum qemu-execution.json > SHA256SUMS)
echo "HIL-A1.5 GitHub-hosted QEMU: PASS; SWPC/Z2 hardware: NOT_RUN"

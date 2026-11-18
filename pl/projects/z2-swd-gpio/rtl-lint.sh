#!/usr/bin/env bash
# Strict enough to detect RTL elaboration/width/latch errors; no Vivado needed.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
pl_dir="$(cd "$script_dir/../.." && pwd)"
command -v verilator >/dev/null || {
  echo "FAIL: verilator not found (install Ubuntu verilator)" >&2
  exit 2
}
echo "=== VERILATOR AXI-LITE IDENTITY RTL LINT ==="
verilator --lint-only --sv -Wall -Wno-UNUSEDSIGNAL \
  --top-module pl_identity_axi_lite \
  "-I$pl_dir/sim/identity_constants" \
  "$pl_dir/rtl/bus/pl_identity_axi_lite.sv"

echo "=== VERILATOR GENERATED IDENTITY RTL LINT ==="
# This is the exact, self-contained module source Vivado IP Integrator gets.
# Catch malformed header expansion and source-format errors before SWPC build.
# Generate only disposable host-only Identity RTL. The standalone FPGA artifact
# CLI is retired, but the Python helper is intentionally still importable.
# Do not create a deployable legacy z2-swd-gpio image or shared build output.
generated="$(mktemp -d -t plasma-identity-rtl-lint.XXXXXXXX)"
trap 'rm -rf -- "$generated"' EXIT
python3 - "$script_dir/artifact.py" "$generated" "${PLASMA_BITSTREAM_VERSION:-0.1.0}" <<'PY'
import importlib.util
import sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("plasma_identity_host_helper", sys.argv[1])
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.prepare(Path(sys.argv[2]), sys.argv[3])
PY
verilator --lint-only --sv -Wall -Wno-UNUSEDSIGNAL \
  --top-module pl_identity_axi_lite \
  "$generated/pl_identity_axi_lite.sv"

echo "=== VERILATOR SWD GPIO + IOBUF RTL LINT ==="
# The primitive stub is simulation-only and is never a Vivado synthesis source.
verilator --lint-only --sv -Wall -Wno-UNUSEDSIGNAL \
  --top-module swd_emio_bridge \
  "$pl_dir/sim/IOBUF.sv" \
  "$pl_dir/rtl/site/swd_emio_bridge.sv"

echo "FPGA_RTL_LINT_PASS"

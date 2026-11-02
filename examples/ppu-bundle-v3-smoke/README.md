# PLASMA Bundle v3 — B3 development smoke

This is an **executable Python example** with **three packages**, but it is
**not a qualified device installer**, publisher signature or hardware test.
Only the reviewed Host-only test invokes the smoke script. The Bootstrap engine
must never infer execution permission from the manifest.

| Package | Kind | Requires | Payload |
| --- | --- | --- | --- |
| `ic-catalog` | `ic-catalog` | — | `data/device.json` |
| `programming-profile` | `programming-profile` | `ic-catalog` | `data/geometry.json` |
| `python-smoke` | `python` | `programming-profile` | `python/smoke.py` |

The ZIP deliberately declares packages in reverse dependency order, so that
DAG resolution must stage catalog → profile → Python. Bundle actions are only
`install` and `verify`. No B4 Activation/Rollback.

## Build a deterministic ZIP on a development host

```sh
python3 scripts/ppu-bundle-v3-smoke.py \
  --source-commit "$(git rev-parse HEAD)" \
  --output /tmp/ppu-b3-smoke.zip
```

The builder outputs the ZIP digest. A digest **does not grant installation or
execution permission**. Source commit provenance must be independently
verified by the trusted authorization path.

## Host-only verification and explicit execution

```sh
python3 -m pytest -q software/python/tests/test_ppu_bundle_v3_smoke_execution_gate1.py
```

The test builds the ZIP, verifies the manifest and SHA256, passes through the
existing single Host-only DeploymentCoordinator/Lock/Journal, and stages the
three packages in an isolated temporary directory. Then, and **only** via an
explicit test harness, it runs the reviewed Python script using `sys.executable`.
Expected standard output:

```text
SMOKE_VERSION=0.1.0
ICPN=STM32F103C8T6
FLASH_BYTES=65536
PASS
```

The IC metadata and geometry are **fixture values**, not an approved
programming route or device qualification. No actual IC is probed, erased,
programmed or verified. A Host-only PASS does not demonstrate deployment to
SWPC/Z2, PS runtime activation, FPGA loading, DUT access or L2 support.

## Security / scope

- No production path writes, service restarts, active pointer updates, or
  hardware calls.
- Python file is declared `executable=false` in the canonical Bundle v3 file
  contract. The explicit test harness invokes a reviewed, SHA-verified script.
- Tests verify dependency order, reproducibility, repeat install, corrupted
  fixture detection, checksum denial and fail-closed restart isolation.
- Future Z2 Path 2 B3 installation requires independently authorized device
  installation and separate hardware execution approval.

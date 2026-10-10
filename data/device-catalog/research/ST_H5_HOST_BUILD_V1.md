# STM32H5 pinned ST OpenOCD host-build experiment v1

**State:** experimental Host-only CI, not an installed Production runtime. This work follows approved ST H5/C5 gap PR #792.

## Goal and boundaries

Compile the *exact pinned ST OpenOCD source commit* `c8d973bdad9a6fddb51459eda109b3b95d23b57a` in a clean Ubuntu 24.04 GitHub Actions runner. Ensure the `stm32h5x` driver source and target script have frozen blob SHAs, the binary starts on **x86_64**, the target Tcl configuration parses under a **dummy JTAG** interface without `init` (no device connection), and the existing PLASMA `scripts/openocd-runtime.py` can produce and verify an isolated SHA256-bound archive.

The workflow **does not** run on Z2 ARMv7, does not exercise SWD or the future FPGA PL adapter, does not open an electrical Site, and does not issue any flash, option-byte, reset, power, or security mutation to an IC. JTAG dummy parsing proves **only syntax and driver/config loading**, not SWD or physical compatibility.

## Evidence and supply-chain boundaries

- Clone public upstream ST fork then checkout the full immutable commit (reject drift).
- Reject mismatch in three source Git blob SHAs: H5 target configuration, H5 flash driver implementation, and flash driver registry.
- Log compiler/build diagnostics in GitHub Actions; capture only the machine-readable JSON evidence artifact.
- Use existing OpenOCD Runtime packager and archive verifier **locally inside the ephemeral runner**. Intentionally **do not upload binaries, loader files, or tar.gz archives** pending artifact licensing/distribution review.
- Host runner dependencies are versioned by Ubuntu 24.04 runner and apt at execution time, **not** a bit-reproducible toolchain lock; each binary payload/artifact SHA256 is measured separately. A successful host build cannot qualify a target ARMv7 binary.
- The normal Production OpenOCD and Device Catalog remain untouched, and all hardware readiness flags stay false.

## CI output

A successful workflow yields:

`st-h5-openocd-host-build-v1-evidence-only/h5-host-build-v1-result.json`

Expected safe fields: `status=HOST_BUILD_ONLY`, `host_architecture=x86_64`, immutable `source_commit`, `artifact_sha256`, `payload_sha256`, `offline_jtag_dummy_parse_pass=true`, and **every physical/deploy/promotion field false**.

After this first build passes, the separately approved next work item is **ARMv7 Linux build of the same source**, shared library ABI compatibility and a Plasma SWD adapter binding plan. Neither should silently replace `/opt/plasma/programming-engines/openocd` on deployed Z2.

## Observed CI result

GitHub Actions run `38020833350` / job `114121246138` completed successfully against source commit
`c8d973bdad9a6fddb51459eda109b3b95d23b57a`.

Observed immutable evidence:

- runtime id: `0.12.0-c8d973bdad9a`
- host architecture: `x86_64`
- local runtime artifact SHA-256: `1758f03aef0a9ce6bbd212343622b174a85f0bda446bb2e26763113f460a64db`
- canonical payload SHA-256: `af506c77d06ffb22b178cde078f13f6a8b9272eb101695e1ea1dc00f09dc967e`
- evidence-only upload ZIP SHA-256: `ca329fd05399c9adcda1ccf612410dd58d2c77d2249fee80bc399e6663304129`
- `target/stm32h5x.cfg` parsed successfully with dummy JTAG and no `init`
- `hardware_runtime_ready=false`
- `production_write_authorized=false`

The retained machine-readable receipt is
`data/device-catalog/research/st-h5-host-build-v1-result.json`.
The GitHub artifact is supplementary and may expire; the retained receipt therefore records the evidence boundary without storing or redistributing the vendor-derived binary.

## Local re-run

The complete isolated compilation recipe is in [the dedicated CI workflow](../../../.github/workflows/device-catalog-st-h5-host-build-v1.yml). It intentionally relies on the public ST GitHub repository and runner-installed build dependencies. It never modifies local working directories outside the runner's temporary directory.

**Do not report these Host-only tests as real programming, manufacturing or HIL evidence.**

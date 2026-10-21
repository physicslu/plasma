# Issue #981 — LA2016 isolated Codex worker read-only diagnosis

**Gate 1 scope: source, hosted/offline contract checks and a reviewable PR only. Gate 2 is mandatory before merge or dispatch. No hardware actuation is authorized by this PR.**

## Why

Two [guarded LA2016 runs](https://github.com/physicslu/plasma/actions/runs/39028422170) did not produce a verified Codex request or PWM evidence, while the 2026-10-16 original real KINGST PWM1→CH0 loopback succeeded. The second dedicated-worker attempt failed even after the owner installed the exact SHA256-pinned 19 MB sigrok AppImage into the approved worker location. The existing supervisor intentionally hides preflight errors behind `NO_GO`. More PWM retries will not diagnose that ambiguity.

## New diagnostic event (only after owner Gate 2)

The exact owner-authored Issue #981 comment:

```text
/plasma-codex la2016-diag 981
```

An **independent** workflow `.github/workflows/plasma-codex-la2016-diagnose.yml` validates trusted owner/repository/issue/comment/ref on GitHub-hosted Linux, pins reviewed merged `main` SHA, and schedules only that checkout on the dedicated `SWPC-plasma-codex` nonroot Runner. An arbitrary Issue instruction, an untrusted PR checkout, a similarly named branch or another actor cannot dispatch.

Pull-request and main-push checks are **hosted/offline only**, using `--self-test`. They do not schedule SWPC or talk to hardware. New source becomes dispatchable only after the reviewed workflow merges into `main` and the owner explicitly triggers the exact command.

## What it reads and what it never does

The diagnostic imports only the already-reviewed `scripts/plasma-codex-la2016.py` library and checks:

1. The exact pinned KINGST AppImage SHA256 and executable bit.
2. The uniquely enumerated LA2016 **sysfs** identity, USB device-node DAC bits and passive `fuser` result via the supervisor's existing `kingst_connection()` routine. This does **not** open the USB device.
3. `codex --version` in the **actual Runner job** environment; stdout/stderr suppressed.
4. The optional firmware search directory's **accessibility only**, without publishing or exploring user paths.
5. The production `sandbox_args()` bubblewrap namespace, with a replacement `/dev`, testing that `/dev/bus/usb`, `/dev/mem` and `/dev/uio0` are hidden. It executes only three passive `test ! -e` assertions.
6. If the CLI and namespace checks pass, invokes the previously reviewed **read-only** `codex_request()` with the same fixed, non-actuating public-source capability prompt. The agent's JSON request is validated but never dispatched to the instrument supervisor.

All operations are bounded. The agent stays in the same reviewed read-only bubblewrap environment that hides real devices and masks private Z2 credentials. It has no arbitrary hardware API; no supervisor `run()` function is called. No `sigrok`, PWM configuration, CH0 capture, Hub switching, JTAG, Z2 SSH or FPGA operation occurs.

No `sudo`, host group edit, service restart, driver installation, AppImage download, or path enumeration is performed. The prior 2026-10-16 *.sr is **not** replayed as fresh evidence.

## Returned data / interpretation

The artifact includes only `report.json`, `exit_code`, and `SHA256SUMS`. The sanitized report contains fixed-code statuses such as:

- `pinned_appimage: PASS | PINNED_KINGST_APPIMAGE_NOT_INSTALLED | KINGST_APPIMAGE_SHA_MISMATCH`
- `usb_metadata_dac_owner: PASS | KINGST_UNIQUE_USB_MAPPING_NOT_READY | KINGST_USB_DAC_DENIED | KINGST_BUSY_OR_OWNER_UNCERTAIN`
- `runner_codex_cli: PASS | CODEX_CLI_NOT_IN_RUNNER_PATH | CODEX_VERSION_FAILED`
- `bwrap_usb_isolation: PASS | BWRAP_NAMESPACE_FAILED | CODEX_HOME_NOT_READY | ISOLATION_OR_CODEX_MISSING`
- `codex_readonly_request: PASS | CODEX_EXEC_NOT_SUCCESS | NO_AGENT_REQUEST | INVALID_AGENT_JSON | NOT_RUN_PREREQUISITE`
- `firmware_path: NOT_CONFIGURED_INFORMATIONAL | CONFIGURED_READABLE | CONFIGURED_NOT_READABLE`

The optional firmware directory check is **informational**: missing `SIGROK_FIRMWARE_PATH` alone does not prove the required firmware is absent or that the instrument cannot function. Pass on the complete diagnostic indicates worker **prerequisite readiness only**, not LA2016 functional acceptance. Even `codex_readonly_request=PASS` is an actual model-response qualification, **not** proof of USB PWM control.

`agent_exec=NOT_RUN` in prior hardware reports could mean any prerequisite or subprocess failure before a validated request, not necessarily that the CLI was never launched. This isolated diagnostic disambiguates those stages while suppressing stdout, stderr, credentials, machine paths, serial numbers, USB bus addresses and model responses.

A physical retry is a **separate owner-authorized single action**, never triggered by this workflow. Continue to enforce the existing owner Gate 1/Gate 2 and strict hardware safeguards. Keep the original operator, existing workers and hardware unmodified.

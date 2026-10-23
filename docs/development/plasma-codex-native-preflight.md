# PLASMA Codex Native installation — Path 2 read-only bootstrap

**Status:** Gate 1 bootstrap candidate; Draft, NOT MERGED, SWPC NOT_RUN. This is a separate PR from blocked #1135. It is not a third approval gate.

## Why this is required

Authentic [Run #39941174584](https://github.com/physicslu/plasma/actions/runs/39941174584) failed in Job #120372762671 with `RESUME_CODEX_INSTALL_UNMOUNTED`. The observed Codex CLI command entry is under the dedicated Runner's NVM Node v22.23.2 tree, with CLI version 0.162.1; real Native ELF path, independent checksum/provenance and dynamic dependencies remain unverified. PR #1135 implements a future single-file Native mounting route, but deliberately retains `NVM_NATIVE_SHA256=None` and stays Draft/BLOCKED.

Existing dynamic Path 3 calls Codex (forbidden in this preflight). Existing generic Path 2 runs scripts in an isolated namespace that intentionally excludes the Runner home. Neither can simply be instructed via a free-text objective to inspect the NVM installation. Do not bypass those boundaries or launch a model Session.

## Minimal trusted bootstrap contract

Reuse **only** Issue #981, the existing `/plasma-dispatch work-order 981` dynamic Work Order, trusted-main Dispatcher and `development-execute` Path 2 job on the existing `SWPC-plasma-codex` Runner. No new Workflow, Runner, registry task ID, privileged executor, arbitrary CLI operation or separate owner Gate.

After separate Gate 2 merge authorization, an owner may post an **exact main-event SHA pinned** Work Order with:

```json
{
  "schema": "plasma.development.work_order.v1",
  "execution_path": "path2-cli",
  "capability": "cpu-only",
  "scope": "host-only",
  "native_preflight": "codex-native-install-v1",
  "pr_number": 0,
  "source_sha": "<CURRENT_MAIN_EVENT_SHA>",
  "objective": "Inventory fixed Codex native package metadata, hash and ELF dependencies only.",
  "acceptance": "Read-only sanitized evidence; no model, hardware or installation mutation."
}
```

The actual objective and acceptance text must each meet the existing minimum length. Replace the SHA placeholder only after checking the latest main at posting time. **This sample is NOT an authorization to post now.**

The Dispatcher rejects non-main PR numbers, stale/missing SHA, wrong actor, ref, issue/comment owner, altered scope, unknown selector, arbitrary `script`, `argv`, `project`, `stage`, model Session selector, extraneous keys and replay attempts. Runner rechecks trusted/source SHA, work-order digest, Runner identity, exact Job name, attempt 1 and host-only capability. This fixed branch executes **trusted main** `scripts/plasma_codex_native_preflight.py`; candidate Python is never run and no Codex CLI is invoked.

The read-only collector is locked to the observed NVM Node v22.23.2 global npm layout and the two named upstream Codex packages version 0.162.1. It reads only fixed entry realpath, package JSON name/version/bin, bounded file stat/permissions, SHA-256, fixed ELF headers, and bounded `/usr/bin/file`, `/usr/bin/readelf -lW/-dW`. Raw tool output, home paths, account numbers, package contents, authentication material and raw Node paths do not enter artifacts. Receipt uses fixed categories and SHA-256; it labels itself `provenance=NOT_INDEPENDENTLY_VERIFIED` and `sha256_pin_authorized=false`. A matching checksum measured solely on the Runner is **not** proof of upstream identity or a secure pin.

A missing installed binary, unexpected symlink, writable source, absent package metadata or unsafe executable rejects or reports `INCOMPLETE`; no fallback to arbitrary paths, no npm install, chmod/chown, sudo, real hardware /dev, /sys, /run, or model API. This is a trusted Host read-only **observation exception** from the generic Path 2 Bubblewrap script executor, not an expansion of generic Path 2.

## Run #39960534505 — fail-closed permission diagnostic (Gate 1 candidate)

Original one-time Owner Work Order on [Issue #981](https://github.com/physicslu/plasma/issues/981#issuecomment-6365869067) resulted in actual [Run #39960534505](https://github.com/physicslu/plasma/actions/runs/39960534505): owner `development-authorize` SUCCESS, `development-execute` FAILURE (exit 2), Codex and Resume jobs SKIPPED. Artifact #12503979029 contained only `{"reason":"NATIVE_PATH_PERMISSIONS_DENIED","status":"NOT_RUN_OR_FAIL"}`. No native hash or ELF status was obtained. The fixed Codex CLI entry and expected wrapper-target validation were passed before this error; **the failing path component is UNKNOWN**.

For this **independent, not-yet-merged Gate 1 diagnostic PR**, retain the exact existing `owned_path` rejection policy (root or effective Runner UID and no group/other writable bits) and the same fixed NVM Node/CLI/version/ELF scope. The only added information on that denial is a bounded, hardcoded **sanitized** classification:

- `denial_stage`: `CLI_WRAPPER`, `CLI_MANIFEST`, `PLATFORM_MANIFEST`, or `NATIVE_BINARY`;
- `denial_cause`: `OWNER_MISMATCH` or `PEER_WRITABLE`;
- `denial_component_index`: 1-based position below the configured Runner home, 1–24, **not a path string**.
- The original `reason=NATIVE_PATH_PERMISSIONS_DENIED` and `status=NOT_RUN_OR_FAIL` remain unchanged; `development-execute` still exits **2**. Receipt also says model/hardware `NOT_RUN` and `sha256_pin_authorized=false`.

A diagnostic exception is not evidence that installation is trusted: do **not** run chmod/chown, relax permissions, retarget the Node version, bind NVM/Home, turn off the Runner checks, install tools, launch Codex, or automatically retry. Neither `stat` raw data, owner/group numeric IDs, username, absolute Home path, arbitrary tool stdout nor Auth/Session content is published. Denials that are not the exact permission error retain the existing generic Fail-closed receipt. Synthetic GitHub-hosted tests prove only the classification logic, **not** the actual SWPC failure component.

This Draft PR needs its own exact-HEAD Gate 2 authorization if validated. It does not authorize publishing another Issue #981 Work Order, triggering SWPC or unblocking #1135. After any later merge, a **separate** exact-main owner instruction would be required to perform another real read-only preflight.

## Gate boundary and acceptance

Before any SWPC observation: implement Host-only positive/negative tests, necessary GitHub-hosted CI, exact-HEAD Code Review and a separate Owner Gate 2 for this Draft bootstrap PR. The currently approved Gate 1 explicitly **does not authorize SWPC execution before merge**. A later SWPC execution requires its own clear owner Work Order and main SHA. No automatic retry, background trigger or model Session.

PR #1135 must remain Draft/BLOCKED until independent source/provenance and Native digest can be reviewed and the actual single-file dependency model is established. This bootstrap PR does not certify real E2E nor authorize merging #1135.

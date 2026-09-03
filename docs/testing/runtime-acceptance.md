# Plasma Runtime Acceptance

Status: deployed-integration acceptance baseline

## Purpose

Runtime acceptance verifies a running Plasma stack after normal CI/contract validation. It is intentionally separate from unit tests, browser contract tests, deployment, and hardware acceptance.

Canonical validation layers:

```text
CI / isolated software validation
    -> unit / contract / browser tests

Runtime acceptance
    -> real BFF / Manager / Plasma Gateway / Plasma Server processes
    -> real HTTP/TCP routing
    -> Mock execution provider by default

Hardware acceptance
    -> Z2 runtime
    -> PS <-> PL
    -> PL <-> Site electrical path
    -> real IC EPVR
```

A Runtime Acceptance PASS with the Mock provider does **not** prove FPGA I/O, electrical behavior, socket behavior, or real IC programming.

## Entry point

Run from the repository root:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback
python3 scripts/runtime_acceptance/run.py emode-programming
python3 scripts/runtime_acceptance/run.py job-cancel
python3 scripts/runtime_acceptance/run.py pmode-batch
python3 scripts/runtime_acceptance/run.py eight-site-batch
```

Run the complete managed-software suite:

```bash
python3 scripts/runtime_acceptance/run.py managed-software
```

Default managed BFF prefix:

```text
http://127.0.0.1:5173/api/manager/ppu
```

Override it when necessary:

```bash
python3 scripts/runtime_acceptance/run.py managed-software \
  --base-url http://127.0.0.1:5173/api/manager/ppu \
  --environment mac-manager-swpc-ppu
```

## Scenario contracts

### `ps-loopback`

Proves the managed production prefix reaches the PS diagnostic handler and returns matching payload/CRC evidence.

It does not prove PS <-> PL.

### `emode-programming`

Proves Engineering Programming uses the current server-owned Batch execution boundary through the managed prefix:

```text
Engineering target discovery
    -> Engineering session
    -> POST /api/batches with one immutable Programming Image
    -> server-side Batch execution
    -> authoritative Batch/Site terminal success
    -> underlying Job/Image SHA-256 binding
```

The browser/runtime acceptance client does not sequence Programming Asset cache calls and per-Site Jobs for EMode; those execution semantics belong to the server-side Batch Runtime.

### `job-cancel`

Proves the production operator cancellation authority rather than a test-only direct Job shortcut. The scenario creates a deterministic long-running one-Site server Batch, observes both the Batch Site and its underlying Job in authoritative `running`, then submits:

```text
POST /api/batches/{batch_id}/cancel
```

through the managed BFF prefix. It requires the cancel response to record `cancel_requested=true` and then requires all three execution layers to converge coherently:

```text
Batch -> cancelled
Site  -> cancelled
Job   -> cancelled
```

The low-level PPU `POST /api/jobs/{job_id}/cancel` remains an internal execution mechanism used by the Batch Runtime; it is not the operator authority for this acceptance scenario. The cancel request sends `{}` as its JSON command envelope. A zero-byte POST is not used.

### `pmode-batch`

Proves the server-owned Batch execution boundary for two Sites. The Batch snapshot is authoritative for membership, lifecycle, Site outcome, statistics, and Programming Asset identity. The scenario also resolves the Site Job IDs and verifies both Job results use the Batch Image SHA-256.

### `eight-site-batch`

Selects an Engineering Mock PPU with exactly eight Sites and requires all of the following:

- exactly eight Batch Sites;
- eight distinct active Job IDs;
- an observed snapshot with all eight Sites simultaneously `running`;
- all eight Sites terminate `success`;
- eight logical Program executions and eight attempts;
- zero retries, manufacturing failures, and infrastructure errors;
- all eight Job results use the same Programming Image SHA-256.

This proves the software 8-Site concurrency model only.

## Deterministic Mock policy

Happy-path Programming acceptance must not depend on randomized Mock failures. Scenarios that need Program execution temporarily set:

```text
program.error_rate_per_mille = 0
program.jitter_ms             = 0
```

The original Mock Runtime snapshot is retained in memory and restored in a `finally` path. Restore verification is mandatory. A restore mismatch fails the scenario.

Failure-injection acceptance is a separate concern and should bind an intentional fault profile or deterministic seed rather than reuse a happy-path test.

## Safety boundary

Write-capable scenarios discover targets from the Engineering catalog and allow the Mock provider by default. A non-Mock provider fails closed unless the operator supplies:

```text
--allow-real-hardware
```

That flag is a guardrail override, not an approval mechanism. Repository `AGENTS.md` still governs the required Gate 1 approval for real hardware operations.

Do not add `--allow-real-hardware` to routine CI or unattended post-deployment automation.

## Evidence

Each run writes machine-readable JSON under:

```text
artifacts/runtime-acceptance/<run-id>/
```

Evidence includes, when applicable:

- scenario and PASS/FAIL;
- repository commit;
- environment label;
- managed base URL;
- Facility / PPU / Site identity;
- Engineering session ID;
- Programming Image SHA-256;
- Job and Batch IDs;
- submission/cancel route and terminal Batch/Site/Job state;
- concurrency/statistics evidence;
- Mock Runtime restore evidence.

The evidence directory is intentionally ignored by Git. It is a deployment/test artifact, not repository source.

## CI policy

Runtime acceptance is **not** part of ordinary repository CI. CI may test the harness itself (syntax/import/CLI contract) without connecting to a deployed Plasma stack.

The deployed scenarios require real running processes and environment-specific routing, so a CI PASS must never be reported as Runtime Acceptance PASS.

## Future Z2 acceptance

The next hardware-facing validation should remain layered:

```text
Z2 software node readiness
    -> Managed PS Loopback

PS/PL integration
    -> PL Loopback / FPGA path

real Site / IC
    -> single-Site EPVR
    -> multi-Site
    -> eight-Site physical concurrency
```

Do not collapse these layers into one PASS claim.

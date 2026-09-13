# Software Debt Closure Gate

Date: 2026-09-13

This note defines what `SOFTWARE-DEBT-CLOSED` means before Real PYNQ-Z2 PS-only qualification. It is intentionally a software gate, not a hardware-readiness claim.

## Closed software scope

### A3 — safety cleanup observability

Emergency shutdown failure is authoritative and observable. Remaining intentional `pass` cases are limited to bounded non-authoritative cleanup/control-flow cases such as:

- awaiting a backend task after `asyncio.CancelledError` in the Site Safety cancellation path;
- ignoring `FileNotFoundError` while removing an already-absent Unix socket or temporary file;
- allowing a retry-backoff `TimeoutError` to complete the requested delay.

These cases do not suppress a Site power/reset shutdown failure. Safety-path failures outside the explicit cancellation/absent-file/backoff cases remain subject to error propagation or elevation.

### A4 — Batch runtime contract

The Batch runtime remains a policy inheritance hierarchy:

```text
BatchRuntimeManager
  └── PersistentBatchRuntimeManager
        └── DurableBatchRuntimeManager
              └── PersistentMockAwareBatchRuntimeManager
```

The closure criterion is semantic, not a class-count target. `test_batch_runtime_contract.py` is the authority: all runtime variants must satisfy the shared Batch lifecycle/cancel/not-found contract, with subclasses adding persistence/recovery policy. A future refactor to one concrete runtime class is not required by this gate.

### A5 — Gateway canonicalization

Deployed Phase-3, secure, configured-Mock/Z2-like, and retained Phase-2 startup paths use explicit handler composition and `gateway_runner.serve_handler`. Startup paths must not replace `gateway.PlasmaWebHandler` or another phase module's handler global at runtime.

A regression test enforces that `gateway_phase2.py` contains no canonical-handler reassignment and does not chain into `canonical_gateway.main()`.

### A6 — SWPC final regression evidence

Qualification host: SWPC x86_64 Z2-like PS surrogate.

Observed on 2026-09-13:

```text
sudo bash scripts/plasmactl deploy swpc-z2like   PASS
sudo bash scripts/plasmactl verify swpc-z2like   PASS
PMode                                              PASS
EMode                                              PASS
PS Loop Test                                       PASS
```

The deployment preserved the canonical `/etc/plasma/ppu.yaml` Desired configuration, configured local Mock Programming, and managed Programming ingress. The verification result remains bounded to the x86_64 software/mock PS surrogate.

## Explicitly not closed by this gate

The following remain hardware-stage work and MUST NOT be represented as completed by `SOFTWARE-DEBT-CLOSED`:

- a concrete production `SiteSafetyControl` implementation;
- real OpenOCD erase/program/verify runtime and production launcher;
- PYNQ-Z2 ARMv7 physical qualification of the current release;
- PL/FPGA integration;
- Site electrical power/reset/PWR_GOOD behavior;
- real-IC erase/program/verify evidence;
- 1-Site, N-Site, or 8-Site hardware concurrency evidence.

The Engineering 8×32 topology remains intentional simulation/test infrastructure and is not production topology evidence.

## Gate interpretation

`SOFTWARE-DEBT-CLOSED` means the agreed A1–A6 software-contract risks are closed to the level required to start Real Z2 PS-only qualification. It does **not** mean `z2-full`, hardware runtime, or production programmer readiness.

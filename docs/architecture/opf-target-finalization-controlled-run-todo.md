# PLASMA Target Finalization / Controlled Run Policy — TODO

> **Status: OWNER DECISION RECORDED — TODO / NOT IMPLEMENTED**  
> Date: 2026-11-12 (Asia/Taipei)  
> Scope: OPF Programming Route / Manager / PPU Site Worker / PS-local OpenOCD adapter / Console.  
> This document records the desired behavior only. **No code, Route, Bundle, deployment, or DUT behavior is changed by this document.** A separate implementation Gate 1 and explicit merge/deployment authorizations are required.

## Decision

**Default: do not execute `reset run` after an IC programming Job.** The PPU's responsibility is to erase, program, verify and deliver an auditable receipt; successful verification does **not** grant permission to execute the customer's firmware.

This applies to the future default finalization of EMode's `programming` (every legal E/P/V subset), PMode programming, the legacy `flash_cycle` route when migrated, and independent `read` operations. Do not replace `reset run` with another implicit application-start action such as `resume`, a power cycle, or an unqualified reset-to-run sequence.

**Exceptions are permitted only when explicitly selected/authorized and technically qualified:**

1. **Programming-required controlled boot / run-once** — a particular IC, image, Option/Security change, provisioning step, or vendor programming procedure may require executing a target-side step or allowing the new firmware to boot once to finish the programming transaction. Such a step must be supported by source-locked evidence, represented in the exact qualified IC/Programming Route/Recipe, and explicitly admitted within the Job's authorized sequence. A generic programmer must not infer this need from a successful Verify or from an uploaded Bundle's untrusted declaration.
2. **Long-duration / burn-in / firmware-version test** — an operator may explicitly request a controlled RUN after programming to observe Firmware ID, heartbeat, version changes, or other functional behavior. This is a **separate test purpose**, not a prerequisite for ordinary E/P/V PASS and not a hidden step of routine production programming.

A target ROM bootloader or a RAM-resident Flash programming algorithm executing while the programming Provider performs its qualified work is **not automatically the same as launching the newly programmed user application**. The Provider must document this distinction and its boundaries.

## Required policy model (design TODO)

| Policy intent | Default / authority | Expected treatment |
| --- | --- | --- |
| `NO_AUTO_RUN` | **Default** for ordinary Program, Verify, Erase, READ and `flash_cycle` after migration | Do not issue `reset run`, `resume` or equivalent user-application start. Report `RUN_NOT_REQUESTED`; do **not** claim the MCU is guaranteed halted. |
| `PROGRAMMING_REQUIRED_RUN_ONCE` | Exact IC-specific qualified sequence + explicit authorization | Bounded and reasoned boot/run-once, verify its required completion evidence, then apply a qualified post-step final state. If the step fails/ends unknown, fail closed; no silent restart or program retry. |
| `TEST_RUN` | Explicit operator-authorized long-duration test only | Separately identified start/test operation with purpose, duration, Site, image/version expectation, timeout and stop/recovery contract. Observe heartbeat / Firmware ID where available, without conflating that with Flash Verify. |
| `RESET_ASSERTED` / `POWER_OFF_VERIFIED` | Only when separately qualified Site hardware exists | Stronger non-execution guarantee. Not to be simulated by omission of OpenOCD commands. |

Proposed identifiers above are **design vocabulary, not implemented protocol fields**. Do not add a UI control without end-to-end authorization and evidence semantics.

### Necessary safety distinction

- **No `reset run` ≠ proof that an MCU cannot run.** Debug-session shutdown, unplug/replug, watchdog, USB, external NRST, power sequencing and chip-specific halt behavior may cause execution to resume or restart.
- `reset halt` at the beginning of an OpenOCD programming session is the existing qualified preamble for STM32F103 Flash handling. This policy is about **unrequested application execution at finalization**, not removing necessary target reset/halt preconditions or programming algorithms.
- `SAFE_OFF VERIFIED` means the existing PPU Site/resource safe-off checks passed. It is **not** evidence that the MCU is halted, reset-held, unpowered, or executing.
- A formal **guaranteed not running** product requirement needs a qualified per-Site control/observation method (for example independent NRST hold or power switching, including USB/back-power analysis). Until then, the supported claim is only **application RUN not requested by PLASMA**, not **application cannot execute**.
- On FAIL, Cancel, Timeout or `OUTCOME_UNKNOWN`, do not unconditionally `reset run` as a cleanup convenience. Observe/reconcile actual state and preserve safety and forensic evidence before any operator action.
- The explicit test exception must not silently change ordinary production Job behavior, cause auto-retry of an uncertain write, or weaken Resource/Job Binding/Admission checks.

## Current implementation gap (confirmed in repository)

In `scripts/ppu_site_adapter_abi5.py`:

- `_operation_argv()` appends `-c "reset run"` after E/P/V **and** independent READ actions.
- `_flash_argv()` appends `-c "reset run"` after legacy `flash_cycle`.
- The adapter executes OpenOCD on **Z2 PS**; PL implements SWD transport. Removing a UI button alone cannot implement this policy.

The currently deployed Site 2 flow has real E/P/V + SHA256 + SAFE_OFF evidence, but that does **not** establish default no-run behavior. **Existing code still automatically requests RUN.** This TODO must not be reported as a deployed fix.

Related specifications: `docs/architecture/opf-programming-operations-v1.md`, `docs/development/plasma-embedded.md`, `AGENTS.md`.

## Implementation TODO (separate Gate 1)

- [ ] Audit current OpenOCD command generation, success/failure/finally behavior, Debug/Halt after shutdown, per-Site power/reset ownership, and effects of READ and legacy `flash_cycle`. Document which target states can actually be proven.
- [ ] Specify a default-deny **Target Finalization Policy**, its source of authority (qualified Route/Recipe, not arbitrary Bundle or frontend), allowed state transitions, and the differences between not-requested RUN, halted, held-reset, and off.
- [ ] Propagate explicit intent through Manager plan, Job Binding, PPU admission, Site Worker, Provider/OpenOCD and Receipt; reject conflicting/unsupported intent and maintain existing resource identity, safe-off and one-Job execution guarantees.
- [ ] Make `NO_AUTO_RUN` the actual default across EMode, PMode, E/P/V subsets, READ and applicable legacy routes, **without changing the required `reset halt` programming preamble**.
- [ ] Define and qualify per-IC `PROGRAMMING_REQUIRED_RUN_ONCE`: vendor evidence, target state, step ordering, maximum duration, observed completion, failure policy and terminal state. Permit only explicit, qualified cases. Do not assume that all flash operations need this.
- [ ] Provide a separately authorized `TEST_RUN` for long-duration A/B firmware/version tests. Bound execution, observe heartbeat/ID as test evidence, provide explicit stop/recovery; never treat heartbeat as a substitute for Verify.
- [ ] Keep post-Verify Run/Boot evidence distinct from Program PASS, and preserve the Manager/PPU raw Receipt and diagnostic data. In particular record **requested vs observed** finalization; do not label unverified electrical target state as verified.
- [ ] Add host-only negative tests: default command sequences have no `reset run`/implicit `resume`; unsupported per-IC run is denied; Bundle declarations cannot override policy; FAIL/Cancel/Timeout/Unknown never trigger a hidden RUN; no automatic retry; READ default is non-starting.
- [ ] Plan explicit Site 2 HIL to verify both no-request behavior and authorized test-run behavior using CDC version/heartbeat, SWD observations and (where necessary) NRST/power measurement. Mark absence of physical guarantees `NOT_VERIFIED`, never PASS by inference.
- [ ] Update UI/Manager/Embedded docs and versioned programming qualification when implementation is approved. Review the legacy `flash_cycle` compatibility and migration path before any behavior-changing deployment.

## Acceptance criteria

1. An ordinary production E/P/V or READ Job **does not request `reset run` by default**; no implicit alternative starts the user application.
2. An explicitly authorized and qualified programming-required run-once or burn-in test has a distinct purpose, bounded execution, observable evidence and an explicit terminal-state policy.
3. A PASS receipt differentiates Flash content verification, resource `SAFE_OFF`, requested Target Finalization and observed target state; unobserved state is never upgraded to `VERIFIED`.
4. Failure, cancellation and unknown-outcome handling do not unexpectedly launch firmware or silently retry programming.
5. No implementation/deployment/hardware PASS is claimed by this documentation-only TODO.

**Gate boundary:** Document-only now. No merge into `main`, runtime update, PPU restart, real DUT reset, program, power toggle, or hardware experiment is authorized by this TODO.

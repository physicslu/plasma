# Plasma Programming Execution IR v0

Status: **Pilot deterministic execution-semantics contract**

## Purpose

Programming Execution IR sits between validated IC Support profiles and any future backend compiler. It is intentionally more restrictive than Python/C/pseudocode: arbitrary expressions, loops, and free-form control flow are not part of v0.

```text
Manufacturer evidence
        ↓
Canonical IC Support profiles
        ↓
Canonical semantic validator
        ↓
Programming Execution IR
        ↓
Execution IR semantic validator
        ↓
Future backend compiler / executor
```

The IR is not production firmware and does not authorize hardware execution.

## STM32F103C pilot scope

`stm32f103c-programming-execution-ir-v0.json` covers the current pilot targets:

- `STM32F103C8T6`
- `STM32F103CBT6`

The shared flow model contains:

- `flash_unlock`
- `flash_program_unit`
- `flash_erase_page`
- `flash_mass_erase`
- `flash_lock`
- `option_program`
- `option_erase`
- `rdp_disable_transition`

`rdp_disable_transition` is deliberately marked `runtime_compile_ready=false`. Its destructive authorization, sub-operation error propagation, mass-erase side effect, reset boundary, and re-identification requirement are modeled for validation, but this pilot does not claim that the security transition is ready to compile into a production hardware backend.

## Enforced invariants

The Execution IR validator makes the previously AI-review-only rules deterministic for the represented IR surface:

- `V002` — bit predicates are symbolic `set` / `clear`, eliminating raw mask-vs-literal comparisons such as `CR_LOCK != 1`.
- `V003` — ensure/retry paths require terminal-state observation.
- `V004` — unresolved polling timeout enters `uncertain` controller state.
- `V005` — uncertain timeout terminates the normal path and cannot request normal cleanup.
- `V006` — destructive operations require an explicit authorization barrier; reset-based destructive flows cannot fall through to ordinary programming.
- `V009` — address-bearing operations declare canonical bounds and alignment sources. Concrete runtime-address enforcement remains a backend responsibility.
- `V011` — sub-operation failures and uncertain states propagate.
- `V012` — mode-controlled operations have one explicit normal-path entry/exit pair and remain in mode through completion polling.
- `V013` — status/error flags are explicitly cleared using declared W1C semantics before a new operation is started.

`V010` remains outside v0 until Plasma has a separate execution-policy contract. `V014` remains outside v0 until an AI review-artifact contract exists.

## Trust boundary

The validator checks IR semantics against canonical profile symbols. The STM32F1 Programming Profile therefore declares the status bits and W1C flags used by the IR.

The IR must not introduce undocumented register names or bit names. A model-generated IR candidate is only admissible after deterministic validation.

## Regression strategy

`test_validate.py` starts from the known-good pilot IR and injects failures derived from observed Qwen/Gemma defects:

- raw numeric bit predicate;
- retry without terminal observation;
- timeout incorrectly restoring a known state;
- timeout allowed to continue into cleanup;
- destructive RDP fallthrough;
- missing target address constraints;
- ignored sub-operation error;
- missing operation-mode exit;
- missing stale-status/W1C clearing.

Every mutation must fail with the intended semantic rule ID.

## Commands

From repository root:

```bash
python data/ic-support/execution-ir/validate.py
python data/ic-support/execution-ir/test_validate.py
```

A PASS proves only that the checked-in IR is internally consistent with the represented canonical contract and the implemented deterministic invariants. It is not HIL evidence and it is not permission to enable production hardware programming.

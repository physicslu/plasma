# PPU Z2 privilege boundary — Gate 1 (Host-only)

> **Status:** 2026-10-29 approved Gate 1 Path 1, **candidate capability contract only**. No PPU runtime/Gateway authorization wiring, privileged Bridge, Linux sudoers, hardware access, deployment, or Engineer login changes. This document does **not** assert the Z2 is implementing these roles.
>
> Owner product direction originated in documentation-only [PR #1204](https://github.com/physicslu/plasma/pull/1204), which remains a separate Draft at this decision. Refer to existing [remote-write-security-boundary.md](remote-write-security-boundary.md) for implemented Principal/Secure Gateway details and [ppu-execution-ownership.md](ppu-execution-ownership.md) for current Job lease.

## 1. Boundaries, not three new daemons

The PPU contains one Programming Service and one trusted hardware/OS execution boundary. Three **product capabilities** are planned; Console Controller registration and six-Console capacity are **out of scope** for this PPU Gate 1.

| Product identity | Allowed information/operations | Actual Linux authority |
| --- | --- | --- |
| **Monitor** (Guest-equivalent) | Observe sanitised PPU/Site status, Job progress, public logs, results, non-secret settings. | Read-only application identity; **not** necessarily a Linux guest login. Absolutely no IC physical READ/readback, programming, deployment or privileged shell. |
| **Master** (only one active Console in future) | All programming-related Job controls, IC Erase/Program/Verify/physical READ, protected readback exports, Programming Assets, Engine, Script, Profile, documentation/settings deployments and qualified FPGA Image deploy/reload. | **Not UID 0** and no general sudo/root shell. Normal work must go through the authenticated PPU Programming Service, with tightly scoped reviewed privileged execution where required. |
| **Engineer** (independently enabled maintenance mode) | All Master capabilities plus repair/replace protected Root executables, Linux accounts, OS/permissions/services and root shell for maintenance. | Explicit **Linux Root (UID 0)** maintenance authority. Requires independent trusted authentication/physical-local maintenance activation. Role label alone never proves root or unlocks the service. |

An authorised Master may **request** a privileged operation. The request is not a sudo grant: the trusted service/bridge still validates the requested operation, safe target/path, source/install provenance, current FPGA/PPU ownership, legal electrical conditions and recovery. The privileged tool must never accept free-form command lines or caller-controlled Python module names. Protected Root code replacement and arbitrary Linux OS modification belong to Engineer maintenance, not Master. Engineer root is capable of bypassing userspace locks if deliberately uncooperative; the guard cannot provide isolation from that root.

### Authority handoff (not implemented here)

```text
Console Controller -> existing PPU authenticated Gateway (future Master Registry)
                    -> PPU Programming/Job Manager (existing)
                    -> reviewed narrow privileged Bridge for specific operations (future)
                    -> existing Root Image Guard + Reload exclusion + FPGA/Site driver
Engineer maintenance (local extra authorization) -> real Linux root maintenance,
                                     segregated from normal Console requests
```

Only the registered Master will be allowed to submit product mutations when Console Registry is implemented. A role passed in a REST payload or a string such as `"master"` is **not authentication**. The Host-only `plasma_core.ppu_privilege_policy` mapping is a *declarative capability contract* used in tests; it **must not** be used as a trusted authorization result without verified PPU-side identity, Master generation, session revocation and operational safety.

## 2. Machine-checkable contract

`software/python/plasma_core/ppu_privilege_policy.py` enumerates:

- `PPURole`: `monitor`, `master`, `engineer`.
- `PPUAction`: exact information-only, programming, maintenance action allowlist.
- `role_permits`, `require_role_capability`: pure classification functions, fail closed on unknown/untyped values. They do not check credentials or execute privileged code.
- `execution_boundary`: `information_only`, `programming_service`, `reviewed_privileged_bridge` and `engineer_root_maintenance`.

Current live Secure Gateway still has `viewer/operator/engineer/admin/service` role bundles and `Principal` authorization. **No migration or role deletion in this PR.** Only product-facing labels should later simplify. Keep internal API permission granularity, per-resource scopes and idempotency/audit as necessary. Existing `plasma_wordport_program.py` currently checks `geteuid() == 0`; this contract does not make the actual device programmer non-root capable.

## 3. Protected operation classification

| Product action | Normal access | Additional execution gate / privilege |
| --- | --- | --- |
| View public status/log/result | Monitor / Master / Engineer | PPU-side filtering; no secret or full readback |
| Erase/Program/Verify, target READ, Job start/cancel | Master / Engineer | Programming Service; Exact ICPN/Provider, Site execution and hardware ownership checks |
| Deploy programming Engine/Script/Profile/Asset/documentation | Master / Engineer | Validated paths/formats and install transaction; service must not provide generic shell / protected Root code replacement |
| FPGA Image deploy/reload | Master / Engineer | Reviewed privileged Bridge and existing Root Image/Manifest/Boot/ABI/Owner, Golden recovery and Reload exclusion |
| Protected Root code, Linux accounts/system, root shell | Engineer only | Independently authorized local maintenance plus genuine Root OS privileges |

A successful file hash is evidence of integrity, not evidence that source bytes are trusted, compatible or electrically safe. All-Site quiescence and failed/UNKNOWN states remain hardware decisions.

## 4. Scope, acceptance and deferred wiring

**This Gate 1 changes only source-level classification, documents and Host-only negative/positive tests**. It never touches executable Root Guard, privileged entry `scripts/z2/plasma-path2-root-entry`, `pl/hil/fpga_image_root.py`, Linux accounts/sudoers, installed Z2 or hardware resources.

Minimum Host-only evidence:
1. Monitor can view public data but cannot invoke target READ, Erase/Program/Verify, install/update, FPGA reload or privileged repair.
2. Master can request all programming/deployment capabilities but never OS repair, Root code replacement or Root shell.
3. Engineer is the sole classified role for system repair; Root UID/auth and maintenance-mode activation **are not simulated as granted**.
4. Unknown role/action fails closed and all defined actions are classified.
5. Existing Protected Root Entry rejects arbitrary operation, denies non-root, keeps source pin, and normal Program Session remains distinguished from stricter FPGA maintenance census.

**Unimplemented / not claimed:** Console registration/unique Master and generation, 1+5 live Console admission, real root-enabled Engineer entry, hardware-backed Root Bridge for Master, actual target privilege transfer, FPGA/Site two-process concurrency, physical HIL and production qualification. These require separate integration and exact-hardware evidence. Do not merge/retire an existing enforcement layer simply because the pure Host-only policy tests pass.

See [Z2 Root Guard rule audit](../development/z2-root-guard-rule-audit-gate1.md) for necessary, redundant-candidate and maintenance-only checks.

## Follow-on Gate 1: Master non-root Host-only operation request planning

The subsequent [Master non-root execution/deployment contract](ppu-master-nonroot-execution-gate1.md) adds **planning-only** operation and staged-artifact checks that reuse existing PPU release/Bootstrap and protected Root boundaries. No actual Master registration, Unix privilege transition, or live privileged dispatch is implemented by either Gate 1. Master-deployed Python Scripts must never be treated as reviewed Root executable source merely because their package passes a digest check.

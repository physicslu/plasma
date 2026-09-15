# z2like-demo active Site Job disable live-negative gate

**Date:** 2026-09-15  
**Scope:** H021 follow-up qualification debt, SWPC/QEMU configured-Mock only  
**Status:** Gate implementation; live evidence exists only after the post-merge self-hosted job passes.

## Purpose

The main Browser Runtime deployment gate already proves normal commissioned -> disabled maintenance when the canonical 8-Site QEMU PPU is idle. H021 still records a separate negative requirement:

```text
commissioned -> disabled with active Site Job -> must be blocked
```

This gate exercises that requirement through the real public Manager path instead of inferring it from unit tests.

## Live transaction

The post-merge job:

1. waits until the public Render deployment contains the triggering `main` commit;
2. verifies the canonical SWPC managed Bootstrap projection;
3. requires the canonical `z2like-qemu` registry entry to be commissioned and currently idle;
4. performs verified Bootstrap pairing only to obtain the normal short-lived browser maintenance capability;
5. reads the current Mock Runtime settings and temporarily changes only the Mock erase timing to a deterministic 30-second, zero-error profile;
6. starts one real configured-Mock erase Job on Site 1 through the public Manager -> QEMU Gateway path;
7. waits until Manager fleet observation reports that exact Job as active;
8. attempts `commissioned -> disabled`;
9. requires HTTP 409 with `ppu_busy`;
10. cancels the test Job, waits for terminal/idle convergence, and restores the prior Mock Runtime settings.

The temporary profile update increments the Mock Runtime revision, but the editable settings are restored before PASS.

## Fail-closed boundary

The gate does not fabricate an active state. Disable is tested only after Manager itself publishes the exact live Job ID on Site 1. If Manager allows disable, the gate fails.

There is no force lifecycle transition and no direct publication of either the Bootstrap pairing token or browser maintenance capability. Cleanup uses only the normal Programming cancel path, normal Manager lifecycle gate when needed, and the normal Mock Runtime settings API.

## Qualification result semantics

A PASS closes only this H021 debt:

```text
active Site Job disable rejection -> live SWPC/Render/QEMU evidence
```

It does **not** close the remaining H021 live-negative debt:

```text
forced stale/non-idle maintenance proof rejection
15-minute capability expiry wall-clock rejection
```

It also does not qualify physical hardware.

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

No claim is made for PL/FPGA behavior, target power/electrical behavior, real IC programming, or physical multi-Site concurrency.

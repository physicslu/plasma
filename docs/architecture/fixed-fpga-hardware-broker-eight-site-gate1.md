# PLASMA Fixed Image v1 — Single Hardware Broker and Eight-Site Ownership (Gate 1)

> **Status: Review proposal, Host-only. Not a deployed authorization service.**
> **No FPGA runtime reload or physical UIO/MMIO operations.**
> Distinguish existing [logical execution ownership](../architecture/ppu-execution-ownership.md), current [Host Configuration Owner](../../software/python/plasma_interfaces/configuration_owner.py), and this future Hardware Broker.

## Roles and trust boundaries

```text
Plasma Control Station / Gateway (untrusted request inputs)
            |
     AuthN/AuthZ + Batch/PPU Execution Owner
            |
       Site Worker Adapter(s) via bounded local RPC
            |
 [SOLE Hardware Broker: one process, one verified Board Descriptor]
       |                    |                    |
 per-Site lease 1      per-Site lease 2     ... Site lease 8
       \____________________|___________________/
                            |
                 one Linux UIO mapping
                            |
                 fixed PL Site Engines
       independent BOARD safety I/O (DUT power/OE/NRST)
```

1. **PPU Execution Owner**: one logical owner per active PPU at the authoritative Server boundary; one Batch ID may submit multiple parallel Site Jobs. This is not the physical MMIO lock.
2. **Hardware Broker**: exactly one OS account/process owns the authorized MMIO mapping and global HW policy. It serializes register-level access but MUST NOT serialize all complete programming transactions behind one global lock. It does not expose raw addresses over Gateway or direct worker APIs. No worker may open `/dev/uio*`.
3. **Site Lease**: unique `site_id=1..8`, approved aperture and permission set, owner epoch, boot identity, immutable exact-IC Batch ID/profile, current mapping generation, one active in-flight command. Lease is revoked on terminal Job, Broker fault, restart, resource drift or device image mismatch.
4. **Site Safety Authority**: separately handles individual DUT Power/OE/NRST with an independently safe default, off-PL as required; a PL flag or Host fixture cannot prove the socket is electrically safe.
5. **FPGA Configuration Owner**: **no normal runtime reload** for fixed v1; only a separate maintenance authority can consider firmware updates. Deployed Broker must not contain a generic `reload()` exposed to Site/Batch RPC.

## Batch and concurrency contracts

- **Same exact IC/profile per active PPU batch**. Different serial numbers, MACs, image payload overlays and per-DUT calibration data remain independent. The owner must validate normalized exact IC identity from canonical catalog/admission data, not arbitrary browser strings.
- PPU Site Desired `enabled/interface/target` is persisted config **not** authoritative live applied state. Reconcile it before admission; saving it does not change hardware or silently update the current batch.
- One in-flight **hardware command** per Site, 8 independent logical completion/error namespaces. A shared physical serial/SPI/SWD engine may multiplex multiple Sites but must satisfy bounded starvation/latency acceptance before claiming 8 physical concurrency. `max_supported_sites=8` is capacity, not `site_present_bitmap=0xff`.
- Each Job validates PPU lease, Exact IC, Site lease, protocol capability, Site READY, hardware resource generation and unique sequence. On partial failure, Site enters FAULT; ambiguous global mapping/owner/AXI errors seal **all** PPU admissions. No implicit replay of uncertain programming writes.
- A broker-wide short MMIO mutex protects individual 32-bit accesses and mapping cleanup. A Site-wide transaction mutex protects an entire SWD/SPI command sequence; never hold the global mutex through polling/deadlines. Multiple workers talk through broker IPC; only broker accesses UIO.
- Quiesce requested by maintenance or shutdown: deny new jobs *before* observing active leases; await terminal authoritative Job state; refuse uncommitted or uncertain transaction; independently verify external consumers. In fixed v1, **quiesce is NOT permission for FPGA reconfiguration**.

## State machine and identity

```text
UNINITIALIZED -> VERIFY_BOARD -> VERIFY_IMAGE -> IDLE / READY
                                        |          |
                               ambiguous owner     +--> Site BUSY
                                        |                     |
                                        v                DONE / FAULT
                                      FAULT
READY -> QUIESCE -> [ALL SITE TERMINAL] -> SEALED (not FPGA reload)
                         \-> UNKNOWN -> EXTERNAL_RECOVERY_REQUIRED
```

A restart increments/changes **owner epoch**; persistent/monotonic image mapping generation is broker-managed and reconciled against current boot identity and actual image/resources. In-memory `generation++` alone does not survive process restart; old RPC/leases from another epoch MUST fail. A process-global `flock` only coordinates compliant owners. Site `ACK_SEQ` does not undo FAULT and cannot cross an owner epoch.

No privilege or ownership can be inferred from a user-supplied token. IPC authentication and authorization are separate from operation sequencing; Service/Worker auth scopes must be explicitly constrained when implemented.

## Fail-closed matrix

| Hazard | Decision |
| --- | --- |
| UIO ordinals change (uio0 → uio1) but unique identity matches | Re-enumerate by pinned binding and physical resource, subject to current boot/image admission |
| Missing, conflicting or overlapping UIO resource | PPU FAULT / no MMIO |
| Site ID 0, unpresent Site, duplicate lease | Reject before accessing MMIO |
| Second Batch exact IC while first active | `PPU_BUSY` / deny |
| Stale owner epoch, generation, lease or mismatched `DONE_SEQ` | Reject, reconcile; never replay |
| Current Site BUSY | Site-local denial; other independently ready Sites unaffected |
| Unknown IRQ/DMA or retained mapping owner | Seal global admission until independently cleared |
| AXI SIGBUS, unresponsive Kernel or uncertain write completion | EXTERNAL_RECOVERY_REQUIRED, not a Python auto-retry |
| Site target Power Good / NRST / OE not independently safe | Deny physical Site operation; synthetic Host test can't prove safety |
| User/Worker requests FPGA Load while any Job active or idle | Always reject from normal runtime (fixed Image policy) |

## Verification plan and M1 evidence ladder

**A. Gate 1 Host contract**: ABI geometry/opcode enum, read/write allowlists, UIO renumbering/overlap rejection, exact IC, Site present/ready/capability, generation/epoch, two-/eight-Site synthetic contexts, reservation and invalid-command failure. CI must run without `/dev/uio*` or privileged hardware runner.

**B. M1 documentation review**: pin Board Descriptor sources, wire state diagrams, per-Site Command/FIFO/Error specification, scheduling and service privileges, safe-outside-PL electrical partition; decide UIO Broker vs custom Kernel driver with evidence-based condition for escalation. M1 architecture review is **not** physical safety sign-off.

**C. Later separately approved RTL/HIL**: RTL+Python same ABI register/command vectors, exact Image and Board Descriptor identity, real two-Site SWD/SPI transactions with independent DUT-safe circuitry, queue fairness, no cross-Site corruption; progress to eight Sites after FPGA build reports/resources/throughput are collected. Do not claim current Z2 has a v1 compliant bitstream.

**D. Optional future dynamic switching**: excluded from first-generation Gate 1/M1 scope. Reopen only if fixed universal engine proves insufficient through measured LUT/FF/BRAM, timing or per-Site throughput; requires separate redesign and K0..K5 safety proof.

**M1 verdict under this Gate 1**: `NO_GO_PENDING_ARCHITECTURE_REVIEW`. Gate 2 merges design/test artifacts only; no permission for real MMIO, FPGA reload, deployment or 8-Site qualification.

# PLASMA Programming Profile v2 / Provider-neutral Execution Plan — Host-only Gate 1

**Status:** additive Host-only contract and tests; NOT wired into Manager, Console,
PPU Runtime or Site Worker. No deployment, live Provider invocation, hardware
control, FPGA access, DUT operations or change to existing programming results.

This specification is scoped to the owner-approved Gate 1. It **does not**
establish a third gate, a Profile-approval mechanism or any mandatory
qualification/5 MHz evidence. A Profile is a Controller-local configuration
that its owner can create, edit, save and select independently.

## Scope and overlap

- Reuse the existing Bundle v3 and the installed provider-options schema
  ("plasma.ppu.provider-options.v1"). Never treat this Plan as a substitute for
  verified Package bytes, Active Resource Set or the PPU route resolver.
- Existing "plasma.ppu.provider-capabilities.v2" continues to describe
  target/transport/driver ABI/basic operations. The new additive
  "plasma.opf.provider-execution-capabilities.v1" describes Provider procedures,
  selectable operations, segmentation support and completion side effects.
- Existing "plasma.opf.job-image-binding.v1" stays unchanged and is referenced
  by SHA-256. A future runtime-integrated Job Binding revision MUST bind the
  Plan digest and recheck the exact active Package/Provider/Hardware identity;
  this Host-only Plan does not claim to have done so.
- PR #1502 owns Controller-local IC Catalog management, not the execution Plan
  or Provider Procedure logic. The planned IC identity may reference an
  owner-defined local part number without creating a manufacturer ICPN.
- PR #830 provides data-only ICP/Offline Socket route modeling. It has no
  executable Power hardware or Provider Runtime entitlement. The v2 Profile
  must not duplicate its package-pinout / route catalogs.

## Implemented pure data contracts

Source: software/python/plasma_opf/profile_v2.py.

1. **Profile** ("plasma.programming-profile.v2"):
   - "identity": local profile_id, local part_number, original
     manufacturer_icpn; no approval or qualification fields.
   - "provider": provider ID plus opaque JSON settings. These settings still
     require the **existing** verified Provider-owned options schema check at
     future PPU admission. A pure Profile parser alone cannot validate them.
   - "hardware": optional power_source = external/ppu/fixture.
     External power cannot be driven by Profile hardware actions.
   - "workflow.steps": 1–32 ordered steps. Two kinds only:
     provider.execute and hardware.action. Provider steps are **whole
     procedures**, NOT Provider-internal OpenOCD/Tcl or flash commands.
   - "completion": no post-programming reset and no auto-run; internal resets
     required to enter programming remain Provider-specific.
2. **Provider execution capabilities**
   ("plasma.opf.provider-execution-capabilities.v1"): provider ID, declared
   procedures, supported basic operations, whether a procedure can be
   separately invoked as a segment, and its observable completion effects.
   Future hardware_callback is reserved but **must be false** in Gate 1.
3. **Mock hardware action capabilities**
   ("plasma.opf.hardware-action-capabilities.v1"): available actions and named
   power/reset/signal resources. This is data for Host-only validation, **not**
   hardware identity or proof of real electrical readiness.
4. **Execution Plan** ("plasma.opf.execution-plan.v1"): canonical SHA-256
   snapshots of Profile, execution capabilities, optional mock hardware
   capabilities and the existing Job Binding / Active Asset Set SHA; Job ID
   and Site ID. Plans are immutable canonical JSON bytes and snapshots expose
   copies on read. The Plan holds intent, NOT authorization.

Profiles with no hardware steps compile to one Provider execute segment with
no extra splitting or modification of the Provider's internal commands.
E Mode and P Mode will eventually share this execution model, but are not
connected in Gate 1. Firmware, Job Site, address, repeat and per-device data
remain outside the saved Profile and are supplied through Job/Batch binding.

## Actions (reserved for a later real Hardware Adapter)

| Action | Typed fields | Notes |
| --- | --- | --- |
| power.set | domain_id, state: on/off | not available for external-owned power |
| power.wait_good | domain_id, timeout_ms | only if actual observation exists |
| reset.set | reset_id, state: assert/release | NRST ownership handover required |
| signal.set | signal_id, state: active/inactive/high_z | logical signal, not raw MMIO |
| signal.read | signal_id | target hardware must support reading |
| delay | duration_ms | bounded local delay |

No general scripting language, loops, Tcl injection, raw register address or
dynamic Pin Routing Matrix is supported. Hardware Actions are available only
at Provider boundaries. In-process Provider Hardware Callback is a reserved
design direction, not an executable feature.

## Safety and result model (Runtime integration requirements)

- Site and shared hardware ownership must remain held across steps within
  one Job. A later implementation must enforce safe Provider quiescence
  before crossing a conflicting power/reset/pin boundary.
- Provider Procedure internals remain Provider-owned: OpenOCD may execute its
  complete E/P/V list in one process; an SDK may use its own API. Do not
  force a command-per-step model.
- Provider Procedure capabilities must disclose completion reset/run behavior;
  the Host-only builder rejects a Procedure whose advertised completion
  conflicts with no-reset/no-run policy. This **does not fix** the current
  ABI-v5 OpenOCD adapter, which still ends with "reset run".
- At Runtime integration, result, actual operation evidence, resource release
  and site finalization must be observed separately. A failed or interrupted
  hardware action may require a quarantined Site and UNKNOWN/no blind resend;
  a mocked PASS is not electrical or SWD evidence.
- On-board uses external Target power. Do not claim power-off, VDD measurement,
  stopped CPU or safe physical socket state merely from existing SWD SAFE_OFF.
- PPU must independently validate active exact Bundle/Provider/Hardware
  capability, Provider settings schema, Job Binding/Plan hashes and Site
  admission. No parsed configuration grants execution privileges.

## Host-only validation and limits

software/python/tests/test_opf_profile_v2.py covers canonical identity,
mutability isolation, Provider-neutral Mock Vendor procedure, mock Power
pre/post flow, permitted segmentation, omitted/unsupported resources, malformed
JSON, duplicate keys, wrong types, illegal E/P/V ordering, reset/run conflicts,
unsupported callback and compatibility with existing Bundle/Binding contracts.

Excluded: Manager REST schema changes, actual Provider integration, Runtime
worker changes, real power control, SWPC/Z2/FPGA/DUT testing, deploy, merge.
CI is authoritative for test results; local tests are not represented as
successful until observed.

**Gate 2:** requires exact-head green relevant CI and review of the
Host-only contract. Runtime cutover / post-reset correction / wiring to
Console, Manager and PPU are separately planned follow-up work, not silently
claimed by this PR.

# PLASMA OPP Open FPGA Engine Identity & Compatibility Standard v1 — Gate 1

> Status: Gate 1 design candidate; NOT a deployed ABI, accepted conformance certification, or HIL result.
> Scope: OPP hardware standard and optional OPF Host adapter. Existing SWD ABI v5 and existing runtime/fixed ABI candidates are unchanged.

## Normative architectural boundary

- OPP defines the public FPGA Engine identity, image naming, compatibility and diagnostics rules.
- OPF Core remains usable without FPGA, PPU, Bundle v3, AXI, SPI or USB. Optional OPF Hardware Adapters translate host/engine discovery and transport.
- PPU/Host Hardware Owner exclusively controls image load, actual hardware identity, resource mapping, electrical interlocks and programming admission. No Provider can bypass these controls.
- Third-party implementations may use any FPGA vendor/board and may implement AXI/MMIO, SPI or USB. Conformance is determined by reproducible tests, not a vendor approval list.

## Identities (do not conflate)

| Identity | Meaning | Authority |
| --- | --- | --- |
| engine_id | Stable logical engine function (e.g. `plasma.swd.independent`) | Engine descriptor |
| image_name | Human-readable artifact name containing FPGA device | Artifact metadata |
| image_id | Stable logical image variant, not a filename or chip ID | Versioned manifest / runtime identity |
| build_id | Exact 128-bit build correlation token, never a substitute for SHA256 | Reproducible build record + runtime identity |
| target_fpga_part | Exact implementation part, package and speed grade | Build manifest |
| actual_fpga_device | Observed silicon device identity | Trusted platform-specific Host adapter |
| board_hardware_id/revision | Actual PCB identity/topology, if available | Independent EEPROM/OTP/controlled board descriptor; not image constants |
| engine_abi | Functional command contract version | Engine/adapter pair |
| identity_abi | Identity discovery format version | Discovery contract |

### Image naming

`plasma-<fpga-device>-<engine>-v<semver>` (e.g. `plasma-xc7z020-swd-v1.0.0`).
Do not include `z2` or `pynq` in the logical product image name. Names are for operators, never trusted admission evidence. A build artifact must have an immutable digest and exact part/board/pinout compatibility metadata. Distinct builds may share the same logical image name/version only if the immutable artifact identity distinguishes them unambiguously.

## Minimum common logical identity response

An Engine adapter MUST expose: magic, identity_abi, engine_id/type, engine_abi, image_id, build_id, declared target FPGA part, capability set, implemented site count/presence, health/fault state, and diagnostic read/write capability where supported. Unknown/absent identity must fail closed for programming. A declared FPGA part is not an actual silicon measurement. Capabilities and site count are declarations, not physical qualification.

The common logical response is transport-neutral; **do not mandate AXI registers for SPI/USB Engines**. Where an Engine cannot safely implement writable diagnostics, the adapter MUST report unsupported and the relevant conformance profile must say whether it is mandatory. No diagnostic command may actuate DUT pins, power, reset or erase/program operations.

## MMIO reference identity profile — reuse before extending

For MMIO engines, reuse the existing *candidate* fixed-image identity block from `docs/architecture/fixed-fpga-hardware-abi-v1-gate1.md` rather than allocating a conflicting second map:

| Offset | Existing candidate | Access |
| --- | --- | --- |
| 0x000 | MAGIC = 0x4D534C50 | RO |
| 0x004 | ABI_VERSION = 0x00010000 | RO |
| 0x008..0x014 | IMAGE_ID_W0..W3 | RO |
| 0x018..0x024 | BUILD_ID_W0..W3 | RO |
| 0x028..0x02C | CAPABILITIES_LO/HI | RO |
| 0x030 | SITE_PRESENT_BITMAP | RO |
| 0x034 | SITE_READY_BITMAP | RO |
| 0x038 | PPU_STATUS | RO |
| 0x03C | HW_REVISION (declared, not independently trusted PCB identity) | RO |
| 0x040..0x050 | PPU_ERROR / MAP_REVISION / SITE_STRIDE_BYTES / MAX_TRANSFER_BITS / RESET_CAUSE | RO |

**Open decisions before register freeze:** exact image/build ID word ordering and encoding; how to expose full FPGA part/engine type without breaking legacy offsets; separate identity_abi from existing ABI_VERSION; optional SCRATCH RW offset and no-side-effect semantics; capability enumeration and forward compatibility. These fields are NOT yet standardized in the existing candidate. Do not issue speculative reads/writes to proposed offsets.

SCRATCH is recommended for MMIO conformance only if independently decoded, bounded and side-effect-free; loopback beyond basic transport diagnostics is optional and protocol-specific. A new register addition must be reviewed against actual AXI decode, existing reserved offsets and Linux resource ownership; do not silently claim +0x030 or +0x034 are free.

## OPF-first resolution and admission (normative)

**Do not load an image that is already known unable to execute the requested operations.** OPF Core reasons only about the required programming operations and abstract Engine capabilities. It does not know FPGA part numbers, PCB revisions, bitstream digests, AXI addresses or Golden images.

1. **OPF compatibility resolution, before any load:** resolve Provider/Profile/Operations into required Engine type, operation ABI, capabilities, capacity and Site/resource needs. Ask the optional Hardware Adapter for available Engine descriptors (running or loadable). Reject an incompatible descriptor with `NO_COMPATIBLE_ENGINE`; do not attempt configuration.
2. **Adapter selection:** prefer an already loaded, independently verified compatible Engine. If none is ready, select a loadable Image whose declared capabilities and ABI satisfy the request. This selection does not itself authorize a hardware load.
3. **PPU Host pre-load validation:** validate actual FPGA part, board/pinout/electrical compatibility, artifact digest, resource ownership, safety and recovery prerequisites. These checks belong to the Host, not OPF Core.
4. **Load only if needed:** the Host performs configuration only after both compatibility resolution and hardware admission pass. A programming request does not automatically authorize runtime reload; fixed-image deployments can report `NO_COMPATIBLE_ENGINE` instead.
5. **Post-load verification:** verify observed Engine identity/ABI/build/capabilities against the selected descriptor and receipt. If inconsistent, deny execution; preserve the image for diagnosis only if hardware/electrical ownership and safety remain known.
6. **Execution admission:** OPF confirms the operation contract is still satisfied; Host independently admits exact Site, electrical state and ownership. `FPGA_LOAD_SUCCESS` is not `ENGINE_READY`, and neither proves programming success.

The Host can report an image as loaded but not executable; this is a **diagnostic outcome**, not a reason to knowingly load an incompatible image. Runtime readback may reveal a mismatch that cannot be proven from static metadata alone.

### Responsibility split

| Owner | Normative decision | Not its responsibility |
| --- | --- | --- |
| OPF Core | Operations → abstract Engine requirements, compatibility, execution contract | FPGA model, PCB ID, bitstream load |
| OPF Hardware Adapter | Discover loaded/loadable Engine descriptors and map operations to Engine-specific ABI | Independently authorizing hardware safety |
| PPU Host | Physical platform/image validation, FPGA load, readback, electrical safety, Site ownership | Changing Provider operation semantics |
| OPP Standard | Public Engine descriptor, discovery semantics and conformance | Forcing every vendor to implement AXI |

## Hardware admission details

1. **Pre-load:** obtain actual silicon ID through trusted Host mechanism; verify immutable bitstream digest, exact part/package/speed requirements, board pin mapping, clocks, I/O banks/voltage, and authorized hardware ownership. Missing essential evidence => deny, not guess.
2. **Load:** Host owns the bounded FPGA configuration procedure; this standard grants no reload permission.
3. **Post-load:** read supported identity through a validated resource/transport, verify image/build/ABI/capabilities/site mapping against admitted manifest and load receipt.
4. **Before programming:** independently verify electrical/DIB safety, Site ownership, Provider/Profile compatibility and fault/recovery state. Identity PASS is never a Flash PASS.
5. **Failure codes:** FPGA_DEVICE_MISMATCH, HW_PLATFORM_MISMATCH, IMAGE_BUILD_MISMATCH, ENGINE_ABI_MISMATCH, ENGINE_IDENTITY_UNAVAILABLE, CAPABILITY_UNAVAILABLE; map them to existing public error contracts before introducing wire changes.

## One standard for first-party and third-party Engines

PLASMA-owned RTL and external FPGA implementations MUST pass the same OPP descriptor, adapter and conformance requirements. The PLASMA SWD v5 implementation is a **reference integration candidate**, not automatically OPP conformant and not exempt from validation. No implementation-specific shortcut may be embedded in OPF Core.

### Minimum integration sequence

1. Declare required operations and Engine capabilities independently of FPGA vendor.
2. Implement an Engine and an OPF Hardware Adapter (or use a proven standard Adapter).
3. Publish a versioned Engine Descriptor and paired immutable Image Manifest; the descriptor must be available for **pre-load compatibility resolution**.
4. Run common host-only identity, operation/ABI, resource and negative admission tests.
5. Validate real board/pinout, electrical safety, fault handling and protocol behavior on actual hardware; software-only PASS is not Hardware Qualified.
6. Admit a compatible loaded Engine, or authorize a safe load only when necessary, then verify runtime identity before programming.

### Contract versus optional profiles

- **Common mandatory interface:** discovery, Engine identity and ABI, declared capabilities and Site/resource limits, lifecycle/error semantics, safe failure reporting.
- **Protocol-specific profile:** SWD, SPI, JTAG etc. Only required when that capability is advertised; a device need not implement every protocol.
- **Transport-specific profile:** MMIO, SPI, USB etc. A fixed AXI register map is not a universal OPP requirement.
- **Physical qualification:** board power, pinout, voltage, safe-off and fault isolation require separate actual-hardware evidence.

**Current implementation boundary:** PR #1527 is a Gate 1 identity/compatibility candidate, not a complete public SDK or certified command ABI. The common lifecycle, command ABI, error enumeration and electrical conformance remain to be frozen separately; no claim of plug-and-play interoperability is authorized.

## Cross-application reuse boundary (non-normative direction)

The discovery → requirements resolution → compatibility → Host admission → activation → execution → evidence sequence is **domain-independent in principle**, but this Gate 1 does not create a new generic execution framework. OPP FPGA Engine Identity and compatibility remain reusable building blocks; OPF remains the **programming application** and keeps its existing Provider/Profile/Erase/Program/Verify semantics.

| Reusable boundary | Programming-specific responsibility |
| --- | --- |
| Engine descriptor, immutable build identity and declared capabilities | SWD/SPI/JTAG programming operation semantics |
| Compatibility resolution and already-loaded Engine reuse | Programming Profile, target and route selection |
| Host ownership, image integrity and safe activation | DUT voltage, programming fixture and exact Site admission |
| Lifecycle outcomes and verifiable execution evidence | Erase/Program/Verify results and Flash receipts |

A future ATE, DSP or motion-control application MAY use the same Engine contract and resolution pattern, but MUST define its own operation, timing, safety and result contracts. A generic `ExecutionRequest`, cross-domain scheduler or new universal runtime API is **out of scope** for PR #1527. Do not rename existing OPF APIs or insert an extra abstraction layer solely for hypothetical reuse. Reassess shared interfaces against a second real application before freezing them as platform-wide contracts.

## Conformance profiles

- **Identity Conformant:** normative identity semantics and negative compatibility tests pass.
- **Engine Compatible:** advertised operation ABI and capability-specific negative tests pass.
- **Hardware Qualified:** exact physical board/DIB/power/pinout/operation evidence exists. This is independent from interface conformance and cannot be inferred from Host-only tests.

A non-FPGA Provider remains fully valid OPF Core. Conformance test suites should be public, deterministic and vendor-neutral.

## Existing OPF runtime reconciliation (Gate 1 evidence boundary)

The current `docs/architecture/opf-architecture.md` establishes a **portable Provider contract**, not a mandatory FPGA Engine loader. A Provider with its own transport (e.g. OpenOCD/ST-LINK USB or vendor CLI) must remain usable without a new Hardware Adapter. The optional adapter applies only to a Provider that needs Host-provided Engine capabilities. No universal Router/Runner/Executor, extra Site lock or cross-domain scheduler is introduced here.

For the PPU product route, the existing single authorized Bundle v3 Active Asset Set selects Provider/Profile/FPGA assets; the Host owns Site leases, fencing, image provenance, electrical state, and UNKNOWN recovery. The new OPP descriptor is **not** a second independent asset source or an authorization bypass. An independently hosted OPF application need not use Bundle v3.

The `docs/architecture/runtime-fpga-hardware-abi-v1.md` register map is explicitly **proposed and not present on the current PYNQ Base or deployed SWD ABI v5**. The fixed-image ABI candidate is also not frozen. Consequently, this PR MUST NOT attempt a global identity MMIO read or claim that SWD v5 already supplies `IMAGE_ID`/`BUILD_ID` readback. A bridge for existing SWD v5 may expose verified Host/Bundle metadata as **declared provenance**, but MUST NOT mislabel it as independently observed FPGA runtime identity.

### Smallest real integration delta after candidate acceptance

1. Locate the actual Provider-to-Host capability boundary and its current call sites; reuse it rather than inventing an OPF-wide loader.
2. Represent a selected Engine descriptor separately from Host-observed runtime identity and immutable Image receipt; define which fields are `declared`, `host_verified` or `hardware_observed`.
3. Add a pure compatibility decision ahead of any existing authorized configuration path, with negative tests proving no Host load call on known mismatch.
4. Bind the result to the existing Host ownership and exact-Site admission; no new bypass or reload permission.
5. Only after the real adapter exists, run integration tests against that adapter rather than treating this PR's local Mock functions as product implementation.

**Current verified evidence:** architecture document reconciliation and candidate Host-only tests authored; actual production call-site integration, GitHub Actions PASS, Z2 readback and physical conformance are **NOT_VERIFIED**. These are not implied by a proposed register layout.

### Actual code boundary inventory (read-only, main branch)

- `scripts/ppu_opf_reference_openocd.py`: `ReferenceBinding` carries a `ppu_site_engine.EngineSelection`; `load_engine_verified()` invokes `ppu_site_engine.load_engine()` and caches verified **software/Bundle engine files**. Despite the name, this is not proof that an FPGA bitstream was loaded or independently read back.
- `software/python/plasma_interfaces/base.py`: `BaseInterface` is a per-Site programming hardware boundary with `bind_runtime_job()` trust checks and erase/program/verify/read operations. It is not an FPGA image discovery or configuration API; do not retrofit universal Engine loading into it.
- `software/python/plasma_interfaces/configuration_owner.py`: `ConfigurationOwner` is explicitly a **synthetic Host-only** configuration model. Its `MODEL_LOAD` state never calls a real FPGA Manager and cannot provide live hardware admission evidence.
- The concrete product integration seam to investigate next is the `ppu_site_engine.EngineSelection` / reference route before the existing authorized C-3 worker. Verify the full call graph and actual asset provenance before adding compatibility checks; do not assume `EngineSelection` means PL Engine.

**Naming collision warning:** existing `ppu_site_engine` describes the verified OpenOCD execution engine/toolchain; an OPP **FPGA Engine** is a different resource. Never equate their IDs, ABI, image digest or admission evidence. The smallest safe change may be a separate optional FPGA capability binding, not modifications to `load_engine_verified()`.

## Gate 1 implementation plan (not completed by this document)

1. Reconcile this document with ADR-0009, `runtime_fpga_abi_v1_proposal.json`, `fixed_image_abi_v1_gate1.json`, SWD ABI v5 and existing Image Manifest; identify which contracts are historical or candidates.
2. Freeze minimal transport-neutral identity descriptor and MMIO mapping only after resolving the explicit open decisions above.
3. Add schema/host-only positive and negative tests: wrong XC7Z010/XC7Z020 part, same part/wrong PCB, wrong image digest, stale build ID, ABI major mismatch, unknown capabilities, absent identity, no scratch, third-party non-Xilinx transport.
4. Add optional MMIO RTL identity/scratch only in an independent approved implementation delta; do not change SWD v5, deploy, reload or touch DUT.
5. Run focused tests and exact-head CI; report Gate 2 readiness. Gate 2 approval is required for merge.

## Existing references

- `docs/adr/0009-open-programming-platform.md`
- `docs/architecture/opf-architecture.md`
- `docs/architecture/runtime-fpga-hardware-abi-v1.md`
- `docs/architecture/fixed-fpga-hardware-abi-v1-gate1.md`
- `docs/architecture/ppu-canonical-bundle-packages.md`
- `AGENTS.md`

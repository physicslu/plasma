# Device Catalog Phase 4.9C — STM32G4 Metadata Policy

## Status and scope

Phase 4.9C defines a deterministic canonical-metadata policy for the 25 exact STM32G4 identities retained as Active in Phase 4.9B. It does not admit STM32G4 to Production and does not claim programming-algorithm equivalence, physical qualification, HIL qualification, or runtime support.

The policy boundary is deliberately narrower than the STM32G4 ordering-code grammar. Only code combinations required by the retained 25 Active identities are admitted. Other syntactically plausible STM32G4 combinations fail closed until separately evidenced and governed.

## Authority separation

Two evidence domains remain separate:

1. **Commercial identity/lifecycle authority** — retained Phase 4.9B official ST dual-surface product evidence.
2. **Canonical metadata authority** — explicit official ST datasheet ordering-information tables frozen in `stm32g4-phase4.9c-ordering-authority.json`.

OpenOCD routing is not a metadata authority. The six Phase 4.9A CMSIS aliases are not a metadata authority. Neither source can create, normalize, or promote a commercial identity in this phase.

## Bounded candidate set

Metadata candidates are exactly the 25 retained Active ICPNs from eight Base Devices:

- `STM32G431C6`
- `STM32G441CB`
- `STM32G473CB`
- `STM32G474CB`
- `STM32G483CE`
- `STM32G484CE`
- `STM32G491CC`
- `STM32G4A1CE`

The following deterministic Phase 4.9B targets remain current-source-unavailable exclusions because their canonical ST product pages returned HTTP 404:

- `STM32G411C6`
- `STM32G414CB`
- `STM32G471CC`

HTTP 404 is not interpreted as historical nonexistence. Phase 4.9C does not replace these targets with nearby devices or infer missing metadata from family similarity.

The following exact identities remain excluded because official ST Marketing Status reported Proposal:

- `STM32G441CBT3`
- `STM32G441CBU3`
- `STM32G484CET3`

Temperature/package suffixes do not determine lifecycle. Other `T3` and `U3` identities in the retained set are Active; lifecycle remains an exact-identity manufacturer-evidence decision.

## Official ordering-information authorities

The narrowed ordering semantics are frozen against these official ST documents:

| Series | ST document | Revision | Ordering table | PDF page | Review |
|---|---:|---:|---:|---:|---|
| STM32G431 | DS12589 | 6 | 101 | 194 | text + visual |
| STM32G441 | DS12960 | 5 | 101 | 194 | text + visual |
| STM32G473 | DS12712 | 5 | 119 | 225 | text + visual |
| STM32G474 | DS12288 | 6 | 124 | 232 | text + visual |
| STM32G483 | DS12997 | 4 | 119 | 227 | text; screenshot retrieval cache-miss recorded |
| STM32G484 | DS12983 | 5 | 123 | 231 | text + visual |
| STM32G491 | DS13122 | 4 | 101 | 193 | text + visual |
| STM32G4A1 | DS13268 | 4 | 103 | 198 | text + visual |

The repository authority manifest records the exact official ST URLs, document/revision/table/page bindings, review quality, and only the ordering-code semantics needed by the retained candidate set.

## Pin-count semantic trap

A global `C -> 48 pins` rule is invalid for the retained STM32G4 policy.

For STM32G431/G441 ordering information, pin-count code `C` represents 48/49 pins. Package selection resolves the physical count:

- `C/T` -> LQFP48
- `C/U` -> UFQFPN48
- `C/Y` -> WLCSP49 where explicitly bound by the series authority

The retained identity `STM32G441CBY6TR` therefore decodes to **WLCSP49**, while `STM32G441CBT6` and `STM32G441CBU6` decode to 48 pins. The policy implements package-specific pin-count decoding rather than normalizing `C` globally.

This is a first-principles requirement: pin count is a physical/package property, while the ordering code is only an encoding. The decoder must preserve the manufacturer's actual code semantics, not force a convenient one-to-one shortcut.

## Frozen metadata result

The deterministic policy planner produces 25 metadata-ready rows, with no manual-review or reject decisions:

| Dimension | Distribution |
|---|---|
| Flash | 32 KiB: 2; 128 KiB: 10; 256 KiB: 5; 512 KiB: 8 |
| Package | LQFP: 14; UFQFPN: 10; WLCSP: 1 |
| Pin count | 48: 24; 49: 1 |
| Temperature | -40 to 85 C: 19; -40 to 125 C: 6 |
| Packing suffix | standard: 20; TR: 5 |

Policy baseline SHA-256:

`23e83659d694ad8428eda19d7c570372c86ad40d75be8c6bbb8c16007bd398fd`

The baseline is generated deterministically by `stm32g4_phase4_9c_policy.py`; it is not handwritten.

## Production prestate

The frozen Phase 4.9C Production prestate is:

- exact ICPNs: 610
- Base Devices: 209
- families: STM32F0/F1/F2/F3/F4/F7/G0
- STM32G4 exact ICPNs: 0

The one-off baseline transaction verified the frozen prestate is byte-for-byte identical to the current Production manifest at the transaction boundary.

## Fail-closed controls

The Phase 4.9C tests require:

- all 25 retained Active identities and only those identities enter metadata scope;
- the three HTTP-404 Base Devices cannot be promoted without a new evidence transaction;
- the three Proposal exact identities cannot be promoted to Active;
- `STM32G441CBY6TR` remains WLCSP49;
- unbound package, temperature, and option codes fail closed;
- ordering-authority document/revision/table bindings remain exact;
- STM32G483's missing visual screenshot remains explicitly represented rather than silently upgraded to visual verification;
- OpenOCD and CMSIS remain absent from metadata authority;
- Production write remains false.

## Phase boundary

Phase 4.9C can establish `metadata_ready` for the retained 25 exact identities. It cannot establish support.

Capability/routing admission is deferred to Phase 4.9D. Any later admission phase must separately prove the mapping/capability contract and must preserve the historical 4.9B/4.9C evidence boundaries. Only a later publication phase may update Production.

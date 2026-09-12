# Device Catalog — STM32C0 Phase C0.5 Controlled Publication

## Status and scope

C0.5 is the controlled canonical + Production publication transaction for the **209 exact STM32C0 commercial identities admitted by C0.4**.

The broader manufacturer-verified and metadata-ready set contains 220 exact ICPNs. The remaining 11 are capability-unresolved and are deliberately excluded from publication. Their exclusion is **not** a commercial identity rejection.

Publication changes Device Catalog identity availability only. It does **not** claim programming-algorithm equivalence, Flash-controller/geometry equivalence, option/security semantics, physical target qualification, HIL qualification, or PPU/runtime programming support.

## Frozen inputs

- C0.4 admission-plan SHA-256: `36db8e0c34fdbaf46a2ee6dc8df5a09171f6a4434572f9b2cf49cabf63361056`
- pre-publication Production manifest SHA-256: `903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0`
- pre-publication Production manifest Git blob: `89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`
- pre-publication state: 703 exact ICPNs / 243 Base Devices / 9 STM32 families
- STM32C0 Production rows before: 0

C0.2 and C0.3 historical Production prestates remain immutable replay inputs; they are no longer interpreted through mutable live Production state.

## Deterministic publication result

| Dimension | C0.5 result |
| --- | ---: |
| Manufacturer-verified exact ICPNs | 220 |
| Metadata-ready exact ICPNs | 220 |
| Published STM32C0 exact ICPNs | **209** |
| Published STM32C0 Base Devices | **50** |
| Capability-unresolved exact ICPNs | **11** |
| Production exact ICPNs after | **912** |
| Production Base Devices after | **293** |
| Production STM32 families after | **10** |

Published canonical dataset:

- `stm32c0-commercial-icpn.csv`
- SHA-256 `d473c7a1b3b72b75314732ffd59bf8a8b0a39eaf8d632ba935e9e1b71509f96b`
- Git blob `0bf125dd071312cf31c57cfa7ebe3b29ffdda845`

Post-publication Production manifest:

- SHA-256 `15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420`
- Git blob `8abfcc870e51ac4232cdf8d807828cfe4ff5662d`

Frozen publication proposal SHA-256:

`af207b92efc84d37c04755d0512b521392185f26c4b971f52ed6a7fb9644cf9f`

Publication audit SHA-256:

`b351bb5b1a27c62899b23473001caacc4e8a42e4f2395051ad68468d547e9953`

## Capability-unresolved exclusion

The following 11 exact ICPNs remain manufacturer-verified Active and metadata-ready but are not in Production because C0.4 could not establish a unique accepted OpenOCD ordering-pattern route:

- `STM32C051K8U3`
- `STM32C051K8U3TR`
- `STM32C051K8U6`
- `STM32C051K8U6TR`
- `STM32C051K8U7`
- `STM32C051K8U7TR`
- `STM32C071FBY6TR`
- `STM32C071R8I6N`
- `STM32C071RBI6N`
- `STM32C091RBI6`
- `STM32C092RBI6`

Frozen unresolved exact-set SHA-256:

`32698be0aee4f95360a1b27ddfecd1034d7627e0b223dd8873153b5d96ec5601`

## Transaction mechanics

`publish_stm32c0_phase_c0_5.py` independently replays the historical C0.4 plan from immutable prestates, renders exactly 209 canonical rows using the generic admission writer, constructs the post-publication manifest, and verifies all expected digests.

Post-publication validation hard-locks:

- exact 209-row publication equality with the C0.4 admission set;
- complete exclusion of the 11 unresolved identities;
- exactly 50 published STM32C0 Base Devices;
- canonical CSV SHA-256 and Git blob;
- Production manifest SHA-256 and Git blob;
- proposal and audit digests;
- historical C0.2/C0.3/C0.4 replay;
- canonical writer idempotency;
- current published canonical cannot be re-admitted;
- C071 product-version/package semantics;
- C091/C092 series separation;
- no programming/HIL/runtime overclaim.

## Current catalog consequence

After C0.5 publication, STM32C0 is a Production catalog family and is removed from the cross-family research candidate pool. The current read-only shortlist becomes `STM32L1`, `STM32L0`, `STM32L4`. This is prioritization state only and does not authorize work on those families.

## Authority boundary after publication

After C0.5, `Production` means the 209 exact commercial identities are admitted to the Production Device Catalog with manufacturer-backed metadata and deterministic routing identity.

It still does **not** mean Plasma can physically program those devices. Flash algorithm/geometry, option/security behavior, electrical/socket qualification, real-target HIL, and PPU/runtime programming support remain separate evidence chains.

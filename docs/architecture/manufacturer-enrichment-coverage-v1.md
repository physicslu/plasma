# Manufacturer Enrichment Coverage Framework v1

Status: research architecture baseline  
Scope: coverage measurement and reusable manufacturer-fact composition only  
Runtime authority: none  
Hardware authority: none

## 1. Purpose

Plasma already distinguishes exact commercial identity from programming knowledge.

```text
Device Catalog
  -> exact admitted ICPN identity

Manufacturer Enrichment
  -> operating electrical facts
  -> memory map
  -> programming electrical facts
  -> programming interfaces
  -> Flash geometry / controller semantics

Execution / Qualification
  -> Execution IR
  -> generated programmer
  -> independent software differential
  -> physical HIL
```

This framework makes the second and third layers measurable without fabricating missing facts.

It does not promote any target to runtime or hardware-ready state.

## 2. Coverage levels

Coverage is monotonic. A target cannot claim a higher level unless all lower levels are also satisfied.

| Level | Meaning |
|---|---|
| M0 | Production Catalog exact identity only |
| M1 | Manufacturer Device Profile: operating electrical + memory map |
| M2 | Manufacturer Programming Profile: interfaces + programming electrical + Flash geometry |
| M3 | Manufacturer-derived executable semantics: Execution IR + deterministic code-generation path |
| M4 | Independent software differential: OpenOCD semantic comparison + real-binary software acceptance |
| M5 | Exact-ICPN physical HIL programming qualification |

These levels are evidence coverage only. They do not redefine generic IC Support admission or runtime routing.

## 3. Current baseline

At Framework v1 creation, Production contains **4,629 exact ICPNs** across 28 STM32 families.

Highest achieved level:

| Highest level | Exact ICPNs |
|---|---:|
| M0 | 4,628 |
| M1 | 0 |
| M2 | 0 |
| M3 | 0 |
| M4 | 1 |
| M5 | 0 |

Cumulative coverage:

| At least level | Exact ICPNs |
|---|---:|
| M0 | 4,629 |
| M1 | 1 |
| M2 | 1 |
| M3 | 1 |
| M4 | 1 |
| M5 | 0 |

The single M4 golden reference is `STM32F103C8T6`.

This does **not** mean STM32F103-family siblings are enriched. For example, `STM32F103R8T6` remains M0 until manufacturer evidence explicitly establishes applicability.

## 4. Coverage dimensions

Each exact ICPN exposes independent dimensions in the deterministic coverage inventory:

```text
catalog_identity
manufacturer_device_profile
operating_electrical
memory_map
manufacturer_programming_profile
programming_electrical
programming_interfaces
flash_geometry
execution_ir
generated_programmer
independent_software_differential
physical_hil
```

The highest M-level is derived from these evidence-backed dimensions.

Missing dimensions remain explicit.

## 5. Source-of-truth separation

The coverage registry under:

```text
data/ic-support/enrichment-coverage/evidence-v1.json
```

contains only links to already-existing evidence artifacts.

It is not a second copy of device semantics.

The registry is explicitly:

```text
status = research_coverage_only
runtime_authority = false
hardware_authority = false
```

For the STM32F103C8T6 golden reference it binds:

- frozen manufacturer-only baseline and SHA-256 lock;
- Programming Execution IR;
- deterministic programmer generator and behavior test;
- post-freeze OpenOCD semantic comparison;
- real-OpenOCD binary software-acceptance validator/test;
- no physical HIL evidence.

The coverage validator rechecks these relationships rather than trusting the registry label.

## 6. Reusable manufacturer facts

Family-scale enrichment must not duplicate one full JSON profile per commercial ordering code.

Reusable facts may be scoped as:

```text
exact_icpn
base_device
family
package
flash_controller
```

However, a scope name does **not** grant applicability.

Every reusable scope artifact must contain:

```text
authority = manufacturer_official_only
applicability.mode = explicit_exact_icpns
applicability.exact_icpns = [...]
catalog_constraints
source_locks
facts
```

The critical rule is:

> Family-name similarity, OpenOCD mapping similarity, common package, or common Flash-controller naming can never automatically add an exact ICPN to a manufacturer scope.

Exact applicability must be evidenced and listed.

## 7. Composition contract

The v1 composer is:

```text
data/ic-support/manufacturer_enrichment_scope.py
```

For one target it:

1. validates manufacturer-only authority;
2. requires explicit exact-ICPN applicability;
3. checks catalog constraints against the exact target;
4. verifies source revision / SHA-256 locks when supplied;
5. rejects non-manufacturer evidence as manufacturer truth;
6. merges reusable fact paths;
7. fails closed on conflicting fact values.

A scope that applies to another STM32F1 part is ignored unless the current exact ICPN is explicitly listed.

If a listed target disagrees with a scope's Flash-size/package/base-device constraint, composition fails instead of silently inheriting.

## 8. OpenOCD boundary

OpenOCD can provide independent implementation evidence at M4.

It cannot fill missing M1/M2 manufacturer facts.

Therefore:

```text
OpenOCD target mapping
!= manufacturer VDD evidence
!= manufacturer memory-map evidence
!= manufacturer Flash-controller applicability
```

A target may have an OpenOCD backend mapping while remaining M0.

## 9. Physical HIL boundary

M5 requires an explicit exact-target evidence object with:

```text
physical_programming_qualified = true
```

CI, QEMU, fake subprocess, source comparison, generated code, and real OpenOCD configuration parsing cannot produce M5.

Current M5 count is zero.

## 10. Deterministic reporting

The existing coverage inventory now reports Manufacturer Enrichment separately from broader IC Support coverage.

Examples:

```bash
python data/ic-support/coverage_inventory.py --manufacturer-summary
python data/ic-support/coverage_inventory.py --icpn STM32F103C8T6
python data/ic-support/coverage_inventory.py --icpn STM32F103R8T6
python data/ic-support/coverage_inventory.py --json
```

The complete JSON projection includes every Production ICPN and its missing dimensions.

The summary includes:

- highest M-level counts;
- cumulative at-least-level counts;
- per-vendor highest-level counts;
- per-family highest-level counts.

## 11. Negative controls

Framework v1 permanently tests that:

- family similarity does not imply applicability;
- mismatched Flash size fails composition;
- OpenOCD/non-manufacturer source cannot establish manufacturer facts;
- conflicting shared facts fail closed;
- source revision drift fails closed;
- source SHA-256 drift fails closed;
- implicit applicability is rejected;
- empty applicability is rejected.

## 12. Next transaction

The next intended transaction is **STM32F1 Manufacturer Enrichment Expansion v1**.

It should:

1. select bounded STM32F1 scope(s);
2. establish official manufacturer source locks;
3. prove applicability to explicit exact ICPNs;
4. create reusable scoped facts;
5. compose exact-target profiles;
6. update coverage deterministically;
7. leave execution/HIL claims unchanged unless separately evidenced.

Bulk portfolio enrichment should not begin until this scoped-reuse model proves correct on STM32F1 and then on a second Flash-controller architecture such as STM32G0 or STM32C0.

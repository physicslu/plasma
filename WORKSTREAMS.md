# Plasma Engineering Workstreams

Status: **Current repository ownership contract**

Plasma development is organized into three independent engineering workstreams plus one repository-governance domain. The workstreams may exchange facts through explicit interfaces, but they do not inherit each other's validation state.

The three product/research workstreams are:

1. **SW/PPU** — PPU software, PS runtime, PL integration and product execution.
2. **ICPN** — commercial IC part-number discovery, canonical identity and user-selectable catalog expansion.
3. **AI IC Support** — AI-assisted research for deriving evidence-backed programming knowledge and candidate programming methods from manufacturer documentation.

`REPO` is a fourth, non-product domain for repository-wide documentation, terminology, security and CI-boundary governance.

## 1. First-principles boundary

The three workstreams answer different questions:

```text
ICPN
  "What exact commercial IC may the user select?"

AI IC Support
  "What evidence-backed programming knowledge or candidate method can be derived for an IC?"

SW/PPU
  "What can the Plasma product actually execute and qualify today?"
```

These answers are intentionally independent.

```text
ICPN admitted
    != AI programming method researched
    != OpenOCD supported
    != PPU implemented
    != Socket available
    != electrical qualification
    != HIL / real-IC qualification
```

A valid commercial ICPN may be selectable while one or more execution capabilities remain `unsupported`, `unknown`, `unqualified` or `not tested`.

## 2. Workstream ownership matrix

| Workstream | Primary authority | Primary repository surface | Typical outputs | CI must prove | CI must not imply |
|---|---|---|---|---|---|
| **SW/PPU** | Product execution and deployable runtime | `software/`, `pl/`, product/runtime `scripts/`, `release/` | PS runtime, Plasma Server/Gateway/Manager, Site execution, OpenOCD runtime integration, PL integration, PPU/Z2 packages | software correctness, package integrity, ARMv7/QEMU, network/release/runtime contracts | commercial ICPN admission or AI evidence correctness |
| **ICPN** | Commercial IC identity and selectable inventory | `data/device-catalog/` | exact manufacturer part numbers, canonical metadata, lifecycle evidence, Production manifest | discovery/evidence/policy/admission reproducibility and catalog consistency | programming algorithm support, PPU/Socket/HIL readiness |
| **AI IC Support** | Research into programming knowledge and methods | `data/ic-support/` and bounded AI/evidence tooling | Evidence Packs, applicability, semantic facts, candidate Programming/Geometry/Option/Security profiles, AI benchmark results | evidence integrity, semantic/citation contracts, benchmark isolation and research reproducibility | software runtime support or physical programming qualification |
| **REPO** | Cross-repository governance | docs, terminology/security/CI contracts | documentation integrity, terminology rules, CI ownership rules | repository consistency | any product or hardware capability |

## 3. ICPN workstream

### Authority

`data/device-catalog/` owns the answer to:

> Which exact commercial IC identities are admitted to the Plasma selectable catalog?

A Production ICPN establishes commercial identity and its canonical metadata under the Device Catalog evidence/admission contract.

### Typical lifecycle

```text
manufacturer / source inventory
        -> bounded discovery
        -> retained evidence
        -> metadata policy
        -> read-only admission plan
        -> controlled publication
        -> Production catalog
```

The workstream may record backend mapping information as metadata or capability input, but backend readiness is not the authority for whether a legitimate commercial ICPN exists.

### Non-goals

ICPN admission does not claim:

- programming-algorithm equivalence;
- OpenOCD execution support;
- Plasma native/PL support;
- PPU qualification;
- Socket availability;
- electrical qualification;
- real-IC/HIL success.

## 4. AI IC Support workstream

### Authority

`data/ic-support/` owns AI-assisted research into:

> How can programming behavior, geometry, options, security behavior and related method candidates be derived from manufacturer evidence?

Research artifacts remain evidence/research outputs until an explicit promotion step creates a runtime-owned capability artifact or implementation.

### Typical lifecycle

```text
manufacturer documents
        -> source lock / evidence acquisition
        -> deterministic preprocessing
        -> Evidence Pack / applicability
        -> AI semantic extraction
        -> deterministic semantic/citation validation
        -> candidate programming knowledge / method
        -> review / benchmark / retained research evidence
```

### Non-goals

AI IC Support research does not by itself:

- admit a commercial ICPN;
- change Plasma Server/SiteManager execution;
- implement OpenOCD execution;
- implement PPU/PL programming logic;
- qualify Socket/electrical behavior;
- prove real-IC programming.

## 5. SW/PPU workstream

### Authority

SW/PPU owns executable product behavior:

```text
Control Station / Manager
        -> Plasma Gateway
        -> Plasma Server
        -> SiteManager / SiteWorker
        -> execution backend
        -> PS / PL / target interface
```

It also owns build, packaging, deployment and release qualification for the software/PS side of the PPU.

### Capability state

Runtime support for an ICPN is a separate capability/qualification state. A useful capability model is:

```text
exact ICPN
  +-- OpenOCD mapping/execution: supported | unsupported | unknown
  +-- Plasma native/PL:          supported | unsupported | unknown
  +-- PPU qualification:         qualified | unqualified | not tested
  +-- Socket:                    available | unavailable | unknown
  +-- electrical:                qualified | unqualified | not tested
  `-- HIL / physical:            passed | failed | not tested
```

These states must not be collapsed into the ICPN count.

## 6. Explicit promotion boundaries

Cross-workstream movement is a transaction, not an implicit dependency.

### AI research -> SW/PPU

A research result becomes runtime capability only through an explicit promotion boundary, for example:

```text
retained research evidence
        -> reviewed programming profile / method
        -> runtime-owned capability artifact or implementation
        -> software tests
        -> PPU integration
        -> HIL / physical qualification
```

The exact promotion mechanism is still an architecture item. Until it exists, research data must not be described as production runtime support.

### ICPN -> capability state

A newly admitted ICPN becomes immediately valid as catalog inventory. Capability systems may then resolve or display status for that ICPN. Missing capability does not revoke commercial identity.

## 7. CI ownership

The machine-readable registry is:

```text
.github/ci-workstreams.json
```

The permanent boundary regression is:

```text
scripts/tests/test-ci-domain-boundaries.py
```

The intended topology is:

```text
[ICPN]
  Device Catalog historical/current/family CI

[AI IC Support]
  research / evidence / semantic / benchmark CI

[SW/PPU]
  Python/PL / runtime / PPU / Z2 / release CI

[REPO]
  documentation / terminology / security / CI-boundary contracts
```

A workflow belongs to one primary workstream. Cross-workstream inputs must be explicit and narrow. Broad globs are not an acceptable substitute for an actual dependency model.

## 8. Change-classification rule

Every implementation task or PR should identify one **primary workstream** before code changes begin.

A normal PR should stay inside that workstream. If a change truly spans workstreams, its description must state:

1. the primary workstream;
2. the secondary workstream(s);
3. the exact contract crossing the boundary;
4. why separate PRs would be less correct;
5. which CI gates prove each affected authority.

Do not make a cross-workstream PR merely because two directories are convenient to edit together.

## 9. Branch / PR vocabulary

Use these labels in planning, handovers and status reports:

```text
SW/PPU
ICPN
AI IC Support
REPO
```

Avoid using bare `IC Support` to mean all IC-related work. In Plasma, `ICPN`, `AI IC Support`, and executable `SW/PPU capability` are separate concepts.

## 10. Current transitional architecture debt

Current software still contains a legacy pilot bridge where `software/python/plasma_core/ic_support.py` can read `data/ic-support/`, and non-mock `SiteManager` configurations can instantiate that resolver.

This bridge is not evidence that the research workstream owns runtime behavior. It is an explicit separation debt. A future architecture change should either:

- promote reviewed research output into a runtime-owned capability source; or
- remove the research-data resolver from the production execution path.

Until that is resolved, CI ownership must not be broadened to disguise the coupling.

## 11. Source of truth

- Current exact ICPN inventory: `data/device-catalog/production/icpn-v1-manifest.json`.
- Workstream/CI classification: `.github/ci-workstreams.json`.
- CI trigger/risk architecture: `docs/architecture/ci-cd-validation-architecture.md`.
- AI IC Support research boundary: `data/ic-support/README.md`.
- Executable runtime behavior: source code and tests under the SW/PPU workstream.

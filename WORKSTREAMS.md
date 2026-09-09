# Plasma Engineering Workstreams

Status: **Current repository ownership contract**

Plasma development is organized into three independent engineering workstreams plus one repository-governance domain:

1. **SW/PPU** — executable product/runtime, PS/PL integration and release qualification.
2. **ICPN** — exact commercial IC identity and user-selectable catalog expansion.
3. **AI IC Support** — AI-assisted manufacturer-evidence research for candidate programming knowledge/methods.
4. **REPO** — documentation, terminology, security and CI-boundary governance.

The workstreams may exchange facts only through explicit interfaces or promotion transactions. They do not inherit each other's validation state.

## 1. First-principles boundary

The three product/research workstreams answer different questions:

```text
ICPN
  "What exact commercial IC may the user select?"

AI IC Support
  "What evidence-backed programming knowledge or candidate method can be derived?"

SW/PPU
  "What can the Plasma product actually execute and qualify today?"
```

Therefore:

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
| **SW/PPU** | Product execution and deployable runtime | `software/`, `pl/`, runtime/release `scripts/`, `release/` | PS runtime, Server/Gateway/Manager, Site execution, OpenOCD runtime, PL integration, PPU/Z2 packages | software correctness, package integrity, ARMv7/QEMU, runtime/release contracts | ICPN admission or AI-evidence correctness |
| **ICPN** | Commercial IC identity and selectable inventory | `data/device-catalog/` | exact manufacturer part numbers, canonical metadata, lifecycle evidence, Production manifest | evidence/policy/admission reproducibility and catalog consistency | programming algorithm, PPU/Socket/HIL readiness |
| **AI IC Support** | Research into programming knowledge/methods | `data/ic-support/` | Evidence Packs, semantic facts, candidate Programming/Geometry/Option/Security profiles, AI benchmark results | evidence integrity, semantic/citation contracts, benchmark isolation | software runtime or physical programming support |
| **REPO** | Repository governance | docs, terminology/security/CI contracts | documentation integrity, terminology and CI ownership rules | repository consistency | any product/hardware capability |

## 3. ICPN workstream

`data/device-catalog/` owns the answer to:

> Which exact commercial IC identities are admitted to the Plasma selectable catalog?

Typical lifecycle:

```text
manufacturer/source inventory
        -> bounded discovery
        -> retained evidence
        -> metadata policy
        -> read-only admission plan
        -> controlled publication
        -> Production catalog
```

ICPN admission does not claim programming-algorithm equivalence, OpenOCD execution, Plasma-native/PL support, PPU qualification, Socket availability, electrical qualification, or real-IC/HIL success.

## 4. AI IC Support workstream

`data/ic-support/` owns AI-assisted research into:

> How can programming behavior, geometry, options, security behavior and candidate methods be derived from manufacturer evidence?

Typical lifecycle:

```text
manufacturer documents
        -> source lock / evidence acquisition
        -> deterministic preprocessing
        -> Evidence Pack / applicability
        -> AI semantic extraction
        -> deterministic semantic/citation validation
        -> candidate programming knowledge / method
        -> benchmark / retained research evidence
```

Research artifacts are **not executable product configuration**. AI IC Support does not by itself admit an ICPN, alter SiteManager execution, implement OpenOCD/PL programming, qualify Socket/electrical behavior, or prove real-IC programming.

## 5. SW/PPU workstream

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

Runtime support for an ICPN is a separate capability state:

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

## 6. Explicit AI research -> SW/PPU promotion boundary

Cross-workstream movement is a transaction, not an implicit dependency.

The intended flow is:

```text
AI IC Support retained research evidence
        -> reviewed candidate programming method/profile
        -> explicit promotion decision
        -> SW/PPU-owned runtime capability artifact/implementation
        -> software validation
        -> backend/PPU integration
        -> HIL / physical qualification
```

### Current executable state

As of this contract:

- `software/python/` does **not** automatically read `data/ic-support/`;
- `SiteManager` does **not** create a resolver from AI-research data;
- `plasma_core.ic_support.ICSupportResolver.from_root(...)` requires a caller-selected root and has no repository/environment research fallback;
- a non-Mock Site without an explicitly supplied runtime capability resolver fails closed before Job admission/hardware access;
- there is currently **no Production-promoted SW/PPU runtime capability package**;
- software tests use a SW-owned synthetic F103 capability fixture to test routing/plan/executor mechanics; that fixture is not a support claim.

The historical class/metadata names `ICSupportResolver`, `ResolvedICSupport`, and `resolved_ic_support` are temporarily retained for software compatibility. Their runtime values no longer establish a dependency on the AI IC Support workstream.

## 7. ICPN -> capability state

A newly admitted ICPN becomes immediately valid as catalog inventory. Capability systems may independently report status for that ICPN. Missing capability does not revoke commercial identity or remove the ICPN from user selection.

## 8. CI ownership

Machine-readable ownership registry:

```text
.github/ci-workstreams.json
```

Permanent boundary regression:

```text
scripts/tests/test-ci-domain-boundaries.py
```

Topology:

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

A workflow has one primary workstream. Cross-workstream inputs must be explicit and narrow; broad globs are not an acceptable dependency model.

## 9. Change-classification rule

Every implementation task or PR identifies one primary workstream before changes begin. A normal PR should stay inside that workstream.

If a change truly spans workstreams, its description must state:

1. the primary workstream;
2. the secondary workstream(s);
3. the exact contract crossing the boundary;
4. why separate PRs would be less correct;
5. which CI gates prove each affected authority.

Do not create a cross-workstream PR merely because two directories are convenient to edit together.

## 10. Vocabulary

Use these labels in planning, handovers and status reports:

```text
SW/PPU
ICPN
AI IC Support
REPO
```

Avoid using bare `IC Support` to mean all IC-related work. ICPN identity, AI research and executable SW/PPU capability are separate concepts.

## 11. Source of truth

- Current exact ICPN inventory: `data/device-catalog/production/icpn-v1-manifest.json`.
- Workstream/CI classification: `.github/ci-workstreams.json`.
- CI trigger/risk architecture: `docs/architecture/ci-cd-validation-architecture.md`.
- AI IC Support research boundary: `data/ic-support/README.md`.
- SW/PPU runtime capability boundary: `docs/architecture/ic-support-runtime-resolver.md`.
- Executable runtime behavior: source code and tests under the SW/PPU workstream.

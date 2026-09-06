# H001 — Plasma IC Evidence & Canonical Specification Pipeline

**Date:** 2026-09-06  
**Project:** Plasma Universal Multi-Site IC Programmer  
**Repository:** `physicslu/plasma`  
**Main at handover creation:** `7b961d85a9994267bda86fa20b187651cd78b70f`  
**Status:** Research / engineering foundation  
**Canonical dataset admission:** NO  
**HIL admission:** NO  
**Production admission:** NO

## 1. Purpose

This handover transfers the current state of the Plasma AI-assisted IC Support / Manufacturer Evidence / Canonical Specification workstream to another engineering session.

The governing authority order is:

```text
Manufacturer Evidence
    > Validated Canonical Spec
    > Generated Implementation
    > AI opinion
```

The pipeline is being designed so AI extracts evidence-backed manufacturer-near facts while deterministic code owns relationships, canonical vocabulary, normalization, and fail-closed policy wherever possible.

## 2. Plasma system context

Plasma is a configurable multi-Site IC programming system.

```text
Plasma System
└── Facility
    └── PPU (Plasma Programming Unit)
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Product direction:

- Embedded Linux is the PPU / programmer control processor.
- FPGA PL provides custom programming peripherals and timing-sensitive interfaces.
- The product direction is 8 simultaneous programming Sites per programmer.
- The host UI communicates with the PPU over Ethernet.
- Long-term IC support must scale through reusable evidence/spec/profile infrastructure rather than one bespoke driver per commercial part number.

## 3. Repository operating contract

`AGENTS.md` defines an exact two-gate workflow:

```text
Request
  -> read-only inspection
  -> Gate 1: Plan Approval
  -> autonomous implementation / validation / PR / CI repair
  -> Gate 2: Merge Approval
  -> merge to main
```

There is no third approval gate. CI success does not imply FPGA, HIL, electrical, real-target, or production validation.

## 4. Repository state and recent merged work

Main at handover creation:

```text
7b961d85a9994267bda86fa20b187651cd78b70f
Merge pull request #379
IC Support: derive package hardware relationships deterministically
```

Recent relevant PR sequence:

| PR | Purpose | Result |
|---|---|---|
| #374 | Correct canonical evidence citation-path handling | Merged |
| #376 | Semantic extraction / canonicalization foundation | Merged |
| #377 | Semantic extraction v2 benchmark pipeline | Merged |
| #378 | Structured option-byte semantics v3 | Merged |
| #379 | Deterministic package-hardware relationship derivation v4 | Merged |

## 5. Evidence architecture

Do not create one Evidence Pack per commercial PN. Multiple ICPNs may share the same manufacturer documents and reusable programming evidence.

Current conceptual pipeline:

```text
Locked Manufacturer Evidence
        ↓
Deterministic preprocessing
        ↓
Evidence Unit Catalog
        ↓
EvidencePack
        ↓
ApplicabilityBinding
        ↓
TargetEvidenceBundle
        ↓
AI semantic extraction
        ↓
Evidence-backed manufacturer-near facts
        ↓
Deterministic relationship derivation
        ↓
Deterministic canonicalization
        ↓
Canonical IC Specification
```

Core artifacts:

1. SourceLock
2. Evidence Unit Catalog
3. EvidencePack
4. ApplicabilityBinding
5. TargetEvidenceBundle

Core invariants:

- A source document is preprocessed once per source/toolchain/normalization identity.
- Evidence Packs are reusable across ICPNs.
- One ICPN may bind multiple packs.
- Applicability is evidence-backed; AI does not get authority to guess wildcard applicability.
- UNKNOWN fails closed.
- AI can add Evidence, but cannot remove Evidence.

Keep these states distinct:

```text
Document Applicable
    != Canonical Spec Valid
    != Implementation Valid
    != HIL Valid
    != Production Admission
```

## 6. Evidence precedence and taxonomy

Current rule precedence:

```text
dependency closure
    > MUST_INCLUDE
    > UNKNOWN
    > AI add-only
    > OPTIONAL
    > EXCLUDE
```

`DOCUMENT_EXPLICIT` and deterministic rules are authoritative. `AI_SUGGESTED` remains supplemental only.

Evidence taxonomy includes categories such as DEVICE_IDENTITY, ORDERING, MEMORY_MAP, FLASH, PROGRAMMING, DEBUG, BOOT, RESET, CLOCK, POWER, SECURITY, ELECTRICAL, PIN_MAPPING, ERRATA, REVISION, PERIPHERAL_FUNCTIONAL, UNKNOWN, DOCUMENT_STRUCTURE, PACKAGE_MECHANICAL, and ELECTRICAL_OTHER.

## 7. STM32F103C formal source lock

Source-lock file:

```text
data/ic-support/benchmarks/stm32f103c/source-lock.json
```

Source-lock ID:

```text
stm32f103c-source-lock-v0
```

Locked sources:

```text
st_ds5319_rev20
sha256 = 1e54ce18e6c34c5b4a78986f26e245e143748c721009fc9af5953795c30686bc
bytes  = 1965230
```

```text
st_pm0075_rev2
sha256 = 2296c5d528f71ddc7502baa907a0d6a7473ad10f1c67e8b07bb046f291dd4a8a
bytes  = 302996
```

Benchmark targets:

```text
STM32F103C8T6
STM32F103CBT6
```

## 8. Locked target facts

| Field | STM32F103C8T6 | STM32F103CBT6 |
|---|---:|---:|
| Manufacturer device reference | `STM32F103x8` | `STM32F103xB` |
| Commercial part base | `STM32F103C8` | `STM32F103CB` |
| Flash | 65536 B | 131072 B |
| Page size | 1024 B | 1024 B |
| Page count | 64 | 128 |
| Package family | LQFP | LQFP |
| Pin count | 48 | 48 |

Programming contract:

```text
program_granularity_bytes = 2
unlock_keys = [0x45670123, 0xCDEF89AB]
write_erase_requires_hsi = true
```

Option-byte contract:

```text
region_start = 0x1FFFF800
region_size_bytes = 16
encoding = byte_plus_complement
```

Security contract:

```text
read_unprotect_is_destructive = true
write_protection_granularity_bytes = 4096
```

## 9. Deterministic PDF preprocessing

PDF preprocessing uses:

```text
pdftotext -layout -enc UTF-8
```

The pipeline pins tool identity / fingerprint, locale and normalization behavior, retains physical page identity, and records manifest digests. No semantic/canonical/production admission is performed at preprocessing time.

DS5319 semantic Evidence Pack v0 used physical PDF pages as atomic Evidence Units. Earlier validation recorded:

```text
114 physical pages
45 included
~39.5% retained
10 dependency edges
canonical_dataset_admission = false
production_admission = false
```

## 10. Machine and model topology

### SWPC

SWPC owns the canonical Plasma repo, source locks, evidence preprocessing, benchmark harness, hidden ground truth, scoring, canonicalization, and retained benchmark artifacts.

### Mac M3 Max 48 GB

The Mac owns the local LLM runtime. Primary model for this benchmark line:

```text
qwen3.8:27b-mlx
```

The SWPC reaches Mac Ollama through an SSH reverse tunnel, for example:

```bash
ssh -NT \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R 127.0.0.1:11434:127.0.0.1:11434 \
  gordon@SWPC
```

On SWPC, `http://127.0.0.1:11434` then reaches Mac Ollama.

Do not maintain a second canonical Plasma clone on the Mac for this workflow.

## 11. Context-window conclusions

32K remains a conservative baseline. 64K has been proven sufficient for the current large Reduced evidence benchmark.

Current v4 run:

```text
input_tokens      = 56520
generation_tokens = 2145
num_ctx           = 65536
```

The ~55K–56K input range is a capacity benchmark, not a preferred normal Evidence payload. Target future large Evidence payloads at roughly 20K–40K tokens where practical.

There is no current engineering justification for moving to 96K / 128K / 262K.

`ollama ps` reporting 100% GPU indicates model placement/offload, not necessarily 100% GPU utilization. Swap causality must not be claimed without a controlled baseline.

## 12. AI responsibility model

Preferred responsibility split:

```text
Manufacturer docs
        ↓
AI semantic extraction
        ↓
Evidence-backed manufacturer-near facts
        ↓
Deterministic applicability / relationship derivation
        ↓
Deterministic canonicalization
        ↓
Validated Canonical IC Spec
        ↓
Implementation generation
        ↓
Compiler / static checks / simulation / HIL
```

Do not ask the model to guess private Plasma canonical representations when deterministic code can own the transform.

## 13. Benchmark evolution — v1

The original canonical-like extraction scored:

```text
17/21 = 80.95%
```

Four differences were observed:

- C8 `base_device`
- CB `base_device`
- option region-start representation
- option encoding representation

These were primarily representation-contract problems, not confirmed manufacturer technical hallucinations.

Key lesson: manufacturer-near facts and Plasma canonical identity must be distinct.

## 14. Benchmark evolution — v2

v2 moved generation toward manufacturer-near semantic facts.

Result:

```text
20/21 = 95.24%
```

The only disagreement was `option_contract.encoding_semantics`. Qwen produced a fuller evidence-grounded natural-language description of the byte/complement storage semantics, but the deterministic canonicalizer admitted only a small exact alias vocabulary.

Canonicalization therefore failed closed.

Key lesson: free-form semantic prose is a poor deterministic boundary.

## 15. Benchmark evolution — v3 structured option semantics

v3 replaced free-form option encoding text with:

```json
{
  "logical_value_width_bits": 8,
  "stored_pair_width_bits": 16,
  "companion_value_present": true,
  "companion_relation": "bitwise_not"
}
```

Deterministic mapping:

```text
8 / 16 / true / bitwise_not
        ↓
byte_plus_complement
```

Actual v3 run:

```text
input_tokens      = 56224
generation_tokens = 1920
```

Semantic result:

```text
23/24 = 95.83%
wrong semantic assertions = 0
missing / unknown = 1
```

Missing path:

```text
$.semantic_facts.profile_relationships.package_hardware
```

Canonical result:

```text
24/25 = 96%
wrong assertions = 0
missing / unknown = 1
canonicalization = partial
```

The option-byte structured mapping itself passed.

The unresolved `package_hardware` field exposed the next responsibility problem: `shared` is a Plasma cross-target relationship, not a manufacturer-near fact.

## 16. Benchmark evolution — v4 Relationship Derivation Foundation

PR #379 moved ownership of `profile_relationships.package_hardware` out of AI generation.

The generation schema now emits per-target:

```text
package_hardware.package_family
package_hardware.pin_count
package_hardware.debug_programming_interfaces
```

The bounded interface vocabulary for the current STM32F103C benchmark is `SWD` and `JTAG`.

The AI does **not** emit:

```text
profile_relationships.package_hardware
```

Deterministic comparison rules:

```text
complete + equal     -> shared
complete + unequal   -> different
incomplete           -> unknown
```

`debug_programming_interfaces` is compared as a set, so array order is representation-only.

No free-form matching, substring inference, regex semantic inference, or fuzzy relationship matching is allowed.

## 17. Actual v4 Qwen run

Configuration:

```text
model       = qwen3.8:27b-mlx
arm         = reduced_context
num_ctx     = 65536
max_tokens  = 4096
temperature = 0
seed        = 7
```

Observed runtime result:

```text
Ollama relationship-derivation semantic extraction success
input_tokens      = 56520
generation_tokens = 2145
```

Retained artifact directory:

```text
/storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4/
```

Expected retained files include:

```text
reduced_context.semantic-v4.raw.txt
reduced_context.semantic-v4.run.json
semantic-score.json
canonical.json
canonical-score.json
```

Do not mutate retained run artifacts to manufacture a newer benchmark result. If the contract changes, create a new benchmark version.

## 18. v4 semantic score

Observed:

```text
semantic accuracy:            1.0
literal exact accuracy:       1.0
wrong semantic assertions:    0
representation differences:   0
missing/unknown:               0
uncited assertions:           0
out-of-context citations:     0
```

Semantic contract result:

```text
29 / 29 leaves correct
```

## 19. v4 deterministic relationship derivation and canonicalization

Observed:

```text
status: complete
package_hardware relationship: shared
transformations: 6
unresolved paths: 0
package relationship emitted by AI: false
pin-level programming-hardware admission: false
canonical dataset admission: false
production admission: false
```

The architectural proof is:

```text
AI did not output package_hardware = shared.
AI emitted per-target manufacturer-near facts.
Deterministic code derived package_hardware = shared.
```

## 20. v4 canonical score

Observed:

```text
exact accuracy:               1.0
wrong assertions:             0
missing/unknown:              0
uncited assertions:           0
out-of-context citations:     0
transformations:              6
```

Final v4 classification:

```text
AI manufacturer-near facts:                 29 / 29
wrong semantic assertions:                   0
unknown semantic facts:                      0

package_hardware relationship:               shared
relationship emitted by AI:                  no
relationship derived deterministically:      yes

canonical facts:                            25 / 25
canonical wrong:                             0
canonical unresolved:                        0

Relationship Derivation Foundation:          PASS
```

## 21. What v4 does not prove

Do not generalize the result beyond its evidence boundary.

v4 proves that for this locked STM32F103C case, using DS5319 / PM0075, Reduced 64K, Qwen3.8 27B, and this benchmark contract, the semantic -> deterministic relationship derivation -> canonicalization path produced a complete exact result.

It does **not** prove:

- formal Full-vs-Reduced non-regression,
- cross-vendor generality,
- NXP / Renesas / Microchip / TI / Infineon / GigaDevice / Winbond behavior,
- pin-level minimum programming hardware,
- FPGA implementation correctness,
- OpenOCD implementation correctness,
- HIL correctness,
- production programming safety,
- destructive security-transition safety,
- canonical dataset admission.

## 22. Canonical identity model

Keep these concepts separate:

```text
manufacturer_device_reference
commercial_part_base
icpn
```

Example:

```text
manufacturer_device_reference = STM32F103x8
commercial_part_base           = STM32F103C8
icpn                           = STM32F103C8T6
```

Manufacturer naming and Plasma commercial identity are not interchangeable.

## 23. Option-byte structured semantics

Do not regress to free-form option encoding descriptions.

Current structured semantic facts:

```json
{
  "logical_value_width_bits": 8,
  "stored_pair_width_bits": 16,
  "companion_value_present": true,
  "companion_relation": "bitwise_not"
}
```

Canonicalizer behavior:

```text
complete admitted structure  -> byte_plus_complement
incomplete / unknown         -> unresolved
complete but unrecognized    -> fail closed
```

No fuzzy textual interpretation.

## 24. Citation semantics

A valid evidence citation proves that the cited Evidence was supplied to the model. It does not mechanically prove semantic entailment.

Keep separate:

```text
citation presence
citation in-context validity
semantic entailment
```

The current benchmark verifies the first two. Full automatic entailment validation remains future work.

## 25. Formal A/B status

Formal Full-vs-Reduced non-regression has **not** been demonstrated.

Current successful semantic v2/v3/v4 evidence is Reduced-only. Do not state that Reduced is proven equivalent to Full until paired source-locked trials are completed under the same benchmark contract.

## 26. Known technical debt

`ollama_context_probe.py` has a known control-flow defect: if the Full arm times out, the probe may abort before the Reduced arm runs or before a complete report is produced.

This remains a separate workstream. Do not claim it has been fixed.

## 27. Current relationship ownership boundary

`package_hardware` is now deterministically derived.

The following legacy profile relationships remain AI-emitted in v4:

```text
programming
memory_geometry
option
security
```

Do not assume all four should be migrated with simple raw equality.

## 28. Recommended next phase — Memory Geometry Relationship Derivation Foundation

This is the lowest-risk next migration because the AI already extracts the required per-target facts:

```text
STM32F103C8T6:
  flash_size_bytes = 65536
  page_size_bytes  = 1024
  page_count       = 64

STM32F103CBT6:
  flash_size_bytes = 131072
  page_size_bytes  = 1024
  page_count       = 128
```

The AI should therefore no longer need to decide:

```text
memory_geometry = different
```

Recommended next architecture:

```text
per-target memory facts
        ↓
deterministic comparison
        ↓
memory_geometry = shared / different / unknown
```

Suggested deterministic rules:

```text
complete + equal     -> shared
complete + unequal   -> different
incomplete           -> unknown
```

Recommended Gate 1 scope:

1. Remove `profile_relationships.memory_geometry` from AI generation.
2. Reuse `flash_size_bytes`, `page_size_bytes`, and `page_count`.
3. Add deterministic relationship derivation and evidence propagation.
4. Add regressions for equal, unequal, incomplete, and AI-attempted relationship output.
5. Preserve retained v0-v4 artifacts and regressions.
6. No runtime, HIL, hardware, or production admission.

## 29. Later phase — programming / option / security relationships

Do not automatically copy the memory-geometry equality mechanism to:

```text
programming
option
security
```

These are more naturally driven by reusable profile applicability and evidence-backed target applicability.

Preferred future direction:

```text
EvidencePack
    ↓
ApplicabilityBinding
    ↓
TargetEvidenceBundle
    ↓
target applicability
    ↓
deterministic relationship derivation
```

Conceptually:

```text
same applicable contract        -> shared
different applicable contract   -> different
insufficient applicability      -> unknown
```

The relationship should be a deterministic consequence of evidence-backed applicability, not an LLM opinion.

## 30. Relevant v4 files

Under:

```text
data/ic-support/benchmarks/stm32f103c/
```

Important files:

```text
semantic-extraction-v2.schema.json
semantic-extraction-prompt-v2.txt
semantic-extraction-ground-truth-v2.json
semantic_extraction_v4.py
ollama_semantic_extraction_run_v4.py
score_semantic_extraction_v4.py
canonicalization-contract-v2.json
canonicalize_semantic_facts_v4.py
canonicalize_semantic_run_v4.py
canonical-ground-truth-v2.json
score_canonical_v4.py
test_semantic_v4_relationship_pipeline.py
semantic-v4-relationship-benchmark.md
```

CI path:

```text
.github/workflows/ic-support-validation.yml
```

## 31. Strategic direction beyond STM32F103C

Do not scale by cloning STM32-specific assumptions into every vendor.

Desired long-term architecture:

```text
Manufacturer Evidence
        ↓
Vendor-neutral Evidence taxonomy
        ↓
Manufacturer-near semantic ontology
        ↓
Applicability / relationship engine
        ↓
Canonical IC Spec
        ↓
Generic Programming Execution IR
        ↓
Backend / interface implementation
```

Future vendor onboarding should explicitly challenge the ontology with NXP, Renesas, Microchip, Infineon, TI, GigaDevice, Winbond, and other families. A concept that only works because STM32 documentation is structured a certain way is a design warning.

## 32. Current-state statement

As of this handover:

```text
Source locking                           PASS
Deterministic preprocessing              PASS
Evidence Pack foundation                 PASS
AI semantic extraction foundation        PASS
Evidence citation-path handling          PASS
Structured option semantics              PASS
Option canonical mapping                 PASS
Package-hardware relationship derivation PASS

v4 Qwen semantic score                   29 / 29
v4 canonical score                       25 / 25

Formal Full-vs-Reduced A/B               NOT YET PROVEN
Cross-vendor generality                  NOT YET PROVEN
Pin-level programming hardware           NOT ADMITTED
HIL                                      NOT RUN
Production admission                     NO
```

The main architecture rule to preserve is:

```text
AI extracts manufacturer facts.

Deterministic code owns:
- cross-target relationships,
- canonical vocabulary,
- canonical formatting,
- fail-closed unresolved behavior.
```

## 33. Immediate continuation point for the next session

First confirm repository state rather than trusting this document blindly:

```bash
cd /storage/projects/plasma
git switch main
git pull --ff-only origin main
git log -1 --oneline
```

Then read:

```text
handover/H001-plasma-ic-evidence-canonical-pipeline-2026-09-06.md
data/ic-support/benchmarks/stm32f103c/semantic-v4-relationship-benchmark.md
```

Recommended next engineering discussion:

```text
Memory Geometry Relationship Derivation Foundation
```

Before modifying the repo, follow `AGENTS.md` and obtain a new Gate 1 Plan Approval.

## 34. Compressed continuation state

```text
Manufacturer Evidence
    ↓
AI extracts manufacturer-near facts
    ↓
Deterministic relationship derivation
    ↓
Deterministic canonicalization
    ↓
Canonical IC Spec
```

Current proven locked case:

```text
STM32F103C
Qwen3.8 27B
Reduced 64K
semantic = 29/29
canonical = 25/25
package_hardware relationship derived, not AI-emitted
```

Do not optimize for benchmark percentage. Optimize for evidence traceability, correct responsibility boundaries, deterministic transforms, fail-closed behavior, and eventual cross-vendor generality.

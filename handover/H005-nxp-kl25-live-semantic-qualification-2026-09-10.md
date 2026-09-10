# H005 — NXP KL25 Live Semantic Qualification Handover

**Date:** 2026-09-10

**Project:** Plasma Universal Multi-Site IC Programmer

**Repository:** `physicslu/plasma`

**Main used for conflict-resolution/finalization:** `acfb5c93b07a287245c7af1712d7fd7030719b93`

**PR:** `#453`

**PR branch:** `agent/h004-nxp-kl25-gate57a-handover`

**Predecessor:** `handover/H003-nxp-kl25-evidence-applicability-foundation-2026-09-07.md`

**Latest NXP implementation checkpoint:** PR `#437`, merged as `ff4331b92ee563c8e00dc66b499d9b0e3f9a0e7e`

**Current NXP semantic state:** `READY_FOR_REVIEW`

**Semantic/model admission:** NO

**Canonical dataset admission:** NO

**HIL admission:** NO

**Production admission:** NO

**Destructive security-operation admission:** NO

## 1. Purpose

This handover transfers the NXP KL25 AI IC Support workstream after Gate 5.7A primary-scoped bounded extraction reached `8/8`, `INTEGRITY_PASS`, and `READY_FOR_REVIEW` in a retained live Local AI experiment.

H003 ended at the evidence/applicability foundation. H005 covers the work that followed: source-bound evidence packaging, the Gate 5.6 evidence-boundary correction, bounded semantic extraction, the Gate 5.7 retained failure, the Gate 5.7A primary-scope correction, and the exact starting boundary for Gate 5.8 manufacturer-evidence semantic/citation review.

This document was originally prepared as H004, but another project workstream merged `H004-real-z2-managed-ps-control-station-2026-09-10.md` first. The NXP handover was therefore renumbered to H005. The renumbering is administrative only and does not change NXP engineering conclusions.

Authority order remains:

```text
Manufacturer Evidence
    > Validated Canonical Spec
    > Generated Implementation
    > AI opinion
```

`READY_FOR_REVIEW` is not `QUALIFIED`, and neither means production-ready.

## 2. Plasma system context

```text
Plasma System
└── Facility
    └── PPU
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N (max 8)
```

Product direction:

- embedded Linux PS is the programmer main controller;
- FPGA PL provides timing-sensitive/custom programming peripherals;
- one programmer supports up to 8 IC programming Sites concurrently;
- the upper computer / Control Console communicates with the programmer over Ethernet;
- browser/UI code does not directly drive FPGA programming signals;
- IC support must be derived from reusable evidence/spec/profile infrastructure rather than per-part hard-coded assumptions.

The KL25 work is a deliberate cross-vendor stress test against hidden STM32 assumptions.

## 3. Repository governance

`AGENTS.md` remains authoritative:

```text
Request
  -> minimal read-only inspection
  -> Gate 1: Plan Approval
  -> autonomous implementation / validation / commit / PR / CI repair
  -> Gate 2: Merge Approval
  -> merge
```

There is no third approval gate when work remains inside approved Gate 1 scope.

If this handover conflicts with newer executable code, contracts, tests, or `AGENTS.md`, the newer repository state wins.

## 4. Exact NXP target and manufacturer source lock

Commercial target:

```text
MKL25Z128VLK4
```

Source-lock ID:

```text
nxp-kl25-source-lock-v0
```

Data Sheet:

```text
source_id       = nxp_kl25_ds_rev5
document_number = KL25P80M48SF0
revision        = 5
sha256          = e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b
bytes           = 1280088
```

Reference Manual:

```text
source_id       = nxp_kl25_rm_rev3
document_number = KL25P80M48SF0RM
revision        = 3
document_role   = reference_manual_programming_authority
sha256          = 7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241
bytes           = 6637765
pages           = 807
```

Canonical SWPC source directory:

```text
/storage/projects/plasma-benchmark/nxp-kl25/source
```

Pinned preprocessing:

```text
pdftotext -layout -enc UTF-8
```

Do not substitute another RM revision, regenerated PDF, or unverified download without a new governed source lock.

## 5. Gate 5.6 evidence-boundary release

Active release:

```text
nxp-kl25-evidence-boundary-release-v1
```

Primary Evidence Units:

| Unit | Reference Manual pages |
|---|---:|
| FTFA register model | 422–431 |
| FTFA command sequencing | 435–439 |
| Program Longword | 444–446 |
| Erase Flash Sector | 446–448 |
| Erase All Blocks | 451–452 |
| Flash Security | 454–455 |
| Debug / Security interaction | 149–150 |
| SWD / MDM-AP | 151–157 |

Gate 5.6 corrected Program Longword from historical `444–445` to `444–446`. RM p446 continues the Program Longword table before Erase Flash Sector begins. The old Gate 5.4A failure remains immutable negative evidence and must not be post-hoc repaired.

Release fingerprints:

```text
definition_digest = c9c2ed86a0aa5ccdcc1861a0153d0b79cc94f57a568faa5432d9f0389bb4132f
binding_digest    = 1e88d2bb1cfdae65e6456bca3407d2419a7b2bd391729fd2feae1917ac4be038
bundle_digest     = ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf
manifest_digest   = 03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e
model_context_sha = 8ebeab88b4a1e6c540c8af2d4d1941bdb02f0d31389f92a1d4bc0366103cfaaa
pack_count        = 8
```

## 6. NXP-native ontology boundary

The evidence path must preserve NXP-native concepts:

```text
FTFA
FSTAT
FCCOB / FCCOBn
Program Longword
Erase Flash Sector
Erase All Blocks
FSEC
SWD
MDM-AP
```

Do not project STM32 concepts such as `KEYR`, `FLASH_CR`, `PER`, `MER`, `PG`, `OPTWRE`, or `WRPRTERR` onto KL25.

AI is an untrusted extractor. It does not own target identity, family equivalence, applicability, admission, or manufacturer truth.

## 7. Gate 5.7 — retained negative live evidence

Gate 5.7 introduced one live request per primary Evidence Unit while preserving each unit's admitted dependency closure.

Retained run:

```text
/storage/projects/plasma-benchmark/nxp-kl25/bounded-runs/20260909T061908Z
```

Result:

```text
children       = 7/8
aggregate      = REJECTED_INTEGRITY
qualification  = REJECTED_INTEGRITY
```

Failed child:

```text
unit              = nxp-kl25-debug-security-interaction-v0
error_class       = model_output_invalid_json
error_type        = ModelOutputInvalidJSON
done_reason       = length
input_tokens      = 17496
generation_tokens = 8192
raw_bytes         = 29145
```

The other seven children completed with `done_reason=stop`.

This proved output-budget exhaustion for one unit. It did not prove context-window exhaustion: input was 17,496 tokens and output hit the 8,192 limit inside a 65,536 context envelope.

A reporting defect was also corrected: when integrity fails, semantic screening was not executed and must report `NOT_REACHED`, not `PASS`.

Do not mutate, repair, or overwrite this retained run.

## 8. Gate 5.7A — primary-scoped bounded extraction

The Gate 5.7 result suggested that dependency closure was necessary for interpretation but too permissive as semantic fact authority. Gate 5.7A therefore changed semantic scope rather than increasing the output-token budget.

Contract:

```text
nxp-kl25-live-bounded-qualification-v1.1
```

Execution mode:

```text
live_bounded_primary_scoped_sequential
```

Frozen runtime envelope:

```text
model               = qwen3.8:27b-mlx
num_ctx_per_unit    = 65536
max_tokens_per_unit = 8192
temperature         = 0.0
seed                = 0
timeout_seconds     = 1800
automatic_retries   = 0
primary_unit_count  = 8
```

Primary-scope rules:

```text
fact_generation_authority             = PRIMARY_ONLY
dependency_pages                      = SUPPORTING_CONTEXT_ONLY
every_fact_requires_primary_citation  = true
```

Meaning:

```text
PRIMARY pages
    -> may generate semantic facts

DEPENDENCY pages
    -> may provide explanatory/supporting context
    -> may provide supplemental citation support
    -> may not independently justify dependency-only facts
```

Provider JSON Schema and deterministic replay both enforce the primary-citation requirement. Dependency-only facts fail closed.

## 9. Gate 5.7A successful live experiment

Preflight identity:

```text
target          = MKL25Z128VLK4
bundle_digest   = ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf
manifest_digest = 03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e
pack_count      = 8
Ollama version  = 0.33.3
model           = qwen3.8:27b-mlx
model_digest    = 5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e
```

Retained successful run:

```text
/storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z
```

Result:

```text
children       = 8/8
aggregate      = INTEGRITY_PASS
qualification  = READY_FOR_REVIEW
```

This is strong experimental evidence that constraining semantic fact authority to PRIMARY evidence fixed the observed Gate 5.7 failure mode without changing manufacturer evidence, model, context window, output budget, or retry policy.

It is not proof that every extracted fact is semantically correct.

Do not run a second Gate 5.7A Qwen experiment merely to continue the project. Preserve this successful run as retained evidence.

## 10. Repository checkpoints

Gate 5.6 evidence-boundary correction:

```text
PR #429
merge = d40e307a4ed4df710f564cecf930c6098ece9e6b
```

Gate 5.7 live bounded qualification harness:

```text
PR #432
merge = 3119235f1f934c8591dbe387e7f07d9221cf495e
```

Gate 5.7A primary-scoped bounded extraction:

```text
PR #437
head  = 182022c29f942dedce299871745be6d2da2a2280
merge = ff4331b92ee563c8e00dc66b499d9b0e3f9a0e7e
```

Post-merge CI for `ff4331b9...`:

```text
Repository contracts              #606  PASS
AI IC Support research validation #341  PASS
NXP KL25 semantic runner CI        #73   PASS
```

At H005 conflict-resolution/finalization, `main` was:

```text
acfb5c93b07a287245c7af1712d7fd7030719b93
```

Later unrelated main movement does not change retained KL25 run identity.

## 11. Current admission matrix

| Layer | Status |
|---|---|
| Manufacturer source lock | PASS |
| Evidence boundary | PASS |
| Evidence Pack | PASS |
| Commercial target/applicability binding | PASS |
| Bounded extraction architecture | PASS |
| Primary-scoped semantic contract | PASS |
| Real Local AI extraction | 8/8 PASS |
| Deterministic integrity | PASS |
| Deterministic screening | PASS / `READY_FOR_REVIEW` |
| Manufacturer semantic/citation review | NOT YET PERFORMED |
| Semantic extraction admission | NO |
| Model quality admission | NO |
| Canonical dataset admission | NO |
| HIL | NO |
| Production | NO |
| Destructive security operation | NO |

Critical distinction:

```text
READY_FOR_REVIEW
    != semantic truth proven
    != QUALIFIED
    != canonical admission
    != HIL
    != production
```

## 12. Canonical execution topology

SWPC owns:

- canonical Plasma repository;
- source locks;
- evidence preprocessing;
- benchmark harness;
- deterministic validation logic;
- retained benchmark artifacts;
- scoring and future canonicalization.

Mac owns only the Local AI runtime.

Mac Ollama remains loopback-only. SWPC reaches it through the established SSH reverse tunnel. Do not expose Ollama directly to LAN and do not create a second canonical benchmark copy on the Mac.

Canonical repository:

```text
/storage/projects/plasma
```

Benchmark root:

```text
/storage/projects/plasma-benchmark/nxp-kl25
```

Successful Gate 5.7A run:

```text
/storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z
```

## 13. Immutable evidence rules

Do not:

- edit the retained Gate 5.7 negative run;
- edit the retained Gate 5.7A successful run;
- deterministically "repair" model facts or citations;
- silently increase the 8,192-token output budget and call it equivalent qualification;
- perform automatic model retries inside qualification;
- replace Gate 5.6 source/bundle/manifest bindings without a new governed release;
- treat deterministic screening as semantic truth;
- admit Canonical Spec, HIL, production, or destructive security behavior from Gate 5.7A alone.

## 14. Next engineering phase — Gate 5.8

Next recommended phase:

```text
Gate 5.8 — Manufacturer Evidence Semantic + Citation Review
```

Gate 5.8 should consume the retained successful Gate 5.7A extraction rather than generating another model answer.

The review question is:

> For every extracted fact, does the cited NXP manufacturer evidence actually support the statement at the claimed level of specificity?

Recommended Gate 5.8 Gate 1 scope:

1. Bind review to the exact retained Gate 5.7A run, model digest, bundle, manifest, and aggregate provenance.
2. Produce a deterministic review view mapping every fact to PRIMARY and supplemental citations.
3. Review semantic correctness, citation entailment, atomicity, scope, and NXP terminology against locked manufacturer documents.
4. Record explicit per-fact review outcomes; never rewrite retained model output in place.
5. Fail closed on unsupported, ambiguous, over-broad, cross-vendor, or incorrectly cited facts.
6. Keep canonical/HIL/production/destructive-security admissions false during review.
7. Do not run Local AI again unless a later separately approved experiment requires it.

The exact Gate 5.8 review vocabulary and admission policy must be designed and Gate-1 approved before implementation.

## 15. Recovery commands

Start from canonical main:

```bash
set -euo pipefail
cd /storage/projects/plasma
git fetch origin --prune
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
```

Read-only diagnosis of the retained successful Gate 5.7A run:

```bash
bash scripts/ic-support-kl25-live.sh bounded-primary-diagnose \
  /storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z
```

Do not invoke `bounded-primary-run` again merely to continue the work.

## 16. Gate 5.8 success boundary

Gate 5.8 must not be declared successful merely because JSON parses or deterministic screening passes.

The meaningful checkpoint is manufacturer-evidence review of extracted semantic facts and citations. Only after that review passes should a later gate consider promoting reviewed semantics toward a Canonical IC Specification.

Canonical Spec acceptance remains separate from HIL and production qualification.

## 17. Continuation instruction

Use in a new session:

```text
Read repo handover H005 and continue NXP KL25 Gate 5.8.
```

The next session should first inspect `AGENTS.md`, this H005 handover, current `main`, Gate 5.7A contract/tests, and retained successful run identity before proposing Gate 5.8 changes.

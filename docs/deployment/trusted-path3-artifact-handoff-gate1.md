# Path 3 trusted multi-artifact handoff — Gate 1

Status: **Draft / Host-only / not deployed / not authorized for DUT operation**.
Owner approval: 2026-11-06; tracked by this Draft PR.

## Problem and purpose

Path 3 run [#42188477409](https://github.com/physicslu/plasma/actions/runs/42188477409) correctly stopped before mutation: the Codex child could not download three official GitHub Artifacts (HTTP 401). A CI job's successful conclusion is not sufficient proof that the required artifact bytes reached the SWPC worker.

Extend the **existing** trusted Engineering Dispatcher artifact handoff (currently the single Z2 PS Kit contract) for an **owner-pinned set** of:

1. Z2 PS Kit;
2. OPF Factory artifact;
3. `plasma_swd:5` Engine Candidate.

No new runner, release producer, OpenOCD build, FPGA/Driver change, or physical programming is in scope.

## Invariants to implement and test

- Owner-authorized, exact Work Order binding: identify each artifact by repository, workflow, run ID, artifact ID, actual producer source SHA, and expected GitHub ZIP SHA256. Candidate PR source SHA need not equal main; prove the approved source relation without mislabeling it as main.
- Trusted Dispatcher verifies run status/conclusion, event, branch or candidate PR relation, producer repository, workflow identity, artifact name and uniqueness, unexpired artifact, metadata digest and actual ZIP bytes. Never accept a different successful run, arbitrary URL, renamed artifact, implicit fallback, or publisher assertion as proof.
- Verify archive structure, complete internal SHA256SUMS/sidecars, kit source manifest, Factory provenance/manifest, and Engine binary + Admission SHA (including `plasma_swd:5` ABI identity). Preserve original provenance; do not substitute or repackage payloads.
- Fail closed on missing, duplicate, expired, altered, cross-repository or wrong-producer artifacts; malformed ZIP, unsafe extraction, path traversal, symlink, size excess, digest mismatch, and incomplete payloads.
- `GITHUB_TOKEN` and bearer URLs remain confined to trusted Actions steps. Codex receives only verified, read-only, tightly scoped local file paths/receipts; do not expose credentials, URLs, or raw secrets in Job logs or evidence.
- Preserve the original single-Kit compatibility for its currently authorized scenarios only when necessary for this reviewed handoff; avoid broader compatibility layers or weakened admission. Work Order semantics and trusted-main source pin remain intact.
- Add positive and negative Host-only tests for the three producer types, source/Run/Artifact/SHA pins, token isolation, and metadata-to-payload consistency. Existing Dispatcher and release tests remain green.

## Gate 1 acceptance

A minimal Draft PR on current main with host-only tests and actual GitHub-hosted CI evidence, exact PR HEAD, changed files, and Gate 2 readiness. **No merge, Z2 deployment, FPGA reload, OPF Gen7/Gen8 activation, Flash, Verify or Readback** under this implementation task. Any real hardware continuation requires an independently eligible authorized execution after the handoff is merged and in trusted main.

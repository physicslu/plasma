# PLASMA Issue #981 — Software-only Codex Development Pilot (Gate 1)

## Decision and scope (2026-10-18 Asia/Taipei)

Owner approved the next **Software-only Codex Development Pilot** after the
successful real read-only Codex Pilot run
[39133345492](https://github.com/physicslu/plasma/actions/runs/39133345492)
and the merge of PR #1021. This PR implements **only the first offline,
GitHub-hosted acceptance and trusted-publisher handoff slice**. It is not
the live write-capable Codex deployment, a real model invocation, a
GitHub dispatcher, or a Codex-authored PR.

The exact owner Gate 1 selection for execution actor (ChatGPT or Codex) remains
a separate data item in the existing Engineering Dispatch contract.
This PR uses ChatGPT/GitHub to develop the offline safety harness. A generic
bare "approved" in chat is **not** a signed GitHub Work Order approval bound
to a hash and cannot activate a write-capable worker or claim a live job.
No new GitHub approval comment or claim ref is generated.

## Invariants preserved

- Existing eleven `.github/workflows/plasma-codex-*.yml` legacy workflows,
  including real SWPC read-only Pilot, remain untouched.
- `software-pr` capability stays `runtime_enabled=false`; no Work Order,
  capability policy, GitHub Ruleset, branch protection or credential setting
  is changed by this work.
- Offline contract CI is **GitHub-hosted only**, using repository
  `contents:read` with non-persisted checkout credentials; no Issue/PR
  trigger for live worker, self-hosted runner, model key, devices or network
  instrument access.
- No GitHub ref creation, GitHub PR publication, auto-merge, deployment,
  software service restart, SWPC provisioning, Z2, FPGA, LA2016, USB Hub,
  DUT power or flash occurs.
- The existing SWPC `plasma-codex` identity is NOT a general
  software-writing worker. Some legacy workflows have instrument access.
  A future real software-only Codex worker must be disposable and
  independently isolated from devices and GitHub write credentials.

## Narrow simulated flow

```text
checked-in synthetic software-pr Work Order + capabilities-v1.json
        |
        +-- core Work Order/schema/capability preflight
        |
trusted test fixture in isolated hosted TemporaryDirectory
        |
        +-- initial exact file content + SHA256 snapshot
        |
deterministic FAKE-Codex edit (no real model, no shell)
        |
        +-- independent exact allowlist, file kind and content checks
        +-- nonzero/no-op/unknown file/symlink/binary/oversize => DENY
        |
candidate.patch + candidate-receipt.json + SHA256SUMS
        |
trusted mock PR Publisher rechecks Work Order / content / provenance
        |
        +-- simulated branch + simulated PR (in-memory only)
        +-- replay / forged privilege / changed SHA256 => DENY
        |
mock-publisher-receipt.json
        |
        +-- offline review ONLY (NO GitHub push, NO real PR)
```

The synthetic fixture's only allowed path is
`docs/development/software-pr-pilot/RESULT.md` **inside the temporary
directory**, not in the real repository. The expected edit replaces
`Status: PENDING` with `Status: VERIFIED`. Both contents are fixed by
reviewed Python code. A genuine model's output is not trusted by virtue
of a successful process exit; this is a deliberately tiny canary for
future change admission and artifact handling, not a general code
reviewer or a proof of secure model execution.

Run locally, without any external service:

```bash
python3 scripts/tests/test_plasma_engineering_software_pr_pilot.py
mkdir -p /tmp/plasma-software-pr-artifacts
python3 scripts/plasma_engineering_software_pr_pilot.py \
  --work-order specs/engineering-dispatch/examples/software-pr-issue981-offline-pilot.json \
  --policy specs/engineering-dispatch/capabilities-v1.json \
  --artifacts /tmp/plasma-software-pr-artifacts
(cd /tmp/plasma-software-pr-artifacts && sha256sum -c SHA256SUMS)
```

The hosted workflow also calls `scripts/plasma_engineering_software_pr_broker.py`
after the candidate is produced. It uses a deterministic, in-memory
`MockPublisher` to simulate branch creation and PR publication and
produces `mock-publisher-receipt.json`; no actual GitHub ref/PR is
created. The broker verifies the entire candidate receipt schema,
allowlisted file path, expected patch bytes and SHA256. It rejects
forged access attestations, stale Work Order hashes, token claims,
replay attempts, altered patches and untrusted status flags.

Use a fresh, empty artifact directory. The hosted workflow generates
the artifact in the runner's temporary folder, and GitHub uploads only
the sanitized synthetic candidate files. The output receipt explicitly
reports: `real_codex_executed=false`,
`owner_approval_verified=false`, `github_claim_created=false`,
`github_pr_created=false`, `publisher_enabled=false`,
`runtime_enabled=false`, `os_sandbox_isolation_verified=false`
and `credential_isolation_verified=false`. The simulated broker returns
`MOCK_PR_CREATED_IN_MEMORY_ONLY` and keeps
`github_pr_created=false`.

## Remaining true live-pilot blockers

The offline CI above must not be described as end-to-end real Codex
Software Development or a created Codex-authored PR. Before enabling any
real write-capable worker, independently qualify all of the following:

1. **Owner authorization:** immutable reviewed main/work-order SHA256,
   exact Gate 1 actor choice, trusted GitHub owner metadata and atomic,
   durable one-time claim. The active GitHub claim namespace Ruleset
   (#25329605) seen on 2026-10-18 is not evidence that the intended
   claimant can create exactly once and cannot update/delete; the live
   canary and workflow trigger audit are still independent prerequisites.
2. **OS isolation:** disposable GitHub-hosted (not instrument-capable
   SWPC) worker, verified filesystem, /dev, network and resource limits.
   `codex --sandbox workspace-write` alone does not satisfy this.
3. **Credential separation:** model worker has no GitHub write token,
   no long-lived secret, and no shared claim/PR publishing credential.
4. **Artifact handoff:** only a trusted broker may inspect/replay the
   pinned patch from a verified base, reject out-of-scope or binary
   changes, rerun tests and create a scoped branch and PR. Any PR
   operation requires the broker's own narrowly bounded authorization.
5. **Rollback / provenance:** atomic idempotency, retry and cancellation
   semantics, immutable evidence, SHA256 verification, noninteractive
   tmux or hosted observability, failure reporting and safe abort.
6. **Owner Gate 2:** separate HEAD/current-main/CI/rulesets/mergeability
   review before **merging any** PR; no self-merge.

The first **real Codex software-edit + trusted PR publication** remains
NOT RUN. No one should infer authorization to activate the Dispatcher
or submit a new real-model job from this offline PR.

## Gate 2 checklist for this PR only

Verify exact PR HEAD, current `main`, seven-file scoped diff,
`mergeable_state=clean`, hosted workflows and non-skipped checks,
negative test evidence and zero legacy Codex workflow modifications.
Then ask for explicit owner approval to merge this PR. A separate
operationally qualified real runtime remains NO-GO until prerequisites
are demonstrated; merge is not deployment.

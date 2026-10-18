# PLASMA Engineering Dispatch — Protected Claim Canary (Issue #981)

## Status and authorization boundary

**Gate 1: implementation and offline CI only. No live canary has run.**
PR #1024 delivered deterministic synthetic software PR candidate and Mock
Publisher, **not** genuine Codex development, GitHub claim qualification or
real PR publication.

As of 2026-10-18, live GitHub Ruleset #25329605
"Protect PLASMA engineering dispatch claims" is active with
\`update\`, \`deletion\`, \`non_fast_forward\`, no bypass, exact
\`refs/heads/plasma-engineering-claims/**/*\` selector. The namespace had
zero refs when last inspected. An active Ruleset is not evidence that the
intended claim identity can create a ref exactly once and then cannot change
it. This narrow canary probes that missing fact.

This PR introduces a dormant, independently owner-gated GitHub Actions path.
It is not activated by PR checks, by the PR merge, or by any earlier
\`/plasma-codex pilot 981\` comment. Contract PR CI runs only mocked HTTP
transports, without live GitHub write permission.

### Exact future owner-only trigger (NOT issued in this PR)

\`\`\`text
/plasma-dispatch claim-canary 981
\`\`\`

After a separate authorization for **one irreversible GitHub ref canary**,
the repository owner may post that exact comment *on Issue #981*. The
\`issue_comment: created\` workflow checks GitHub-trusted actor/issue/owner,
event action, full comment body, repository/ref, run ID, and pinned checkout
SHA. A PR comment, altered command, other actor, wrong issue or checkout
staleness fails closed. A GitHub-hosted, read-only authorizer precedes a
**separate hosted claimer job** whose \`contents:write\` token is *never*
given to any Codex, model or software worker. Checkout credentials are not
persisted. The claimer itself repeats event checks, rereads live Ruleset
configuration and refuses any unexpected additional ruleset.

### One-shot probe and evidence

The fixed ref is
\`refs/heads/plasma-engineering-claims/900003/ruleset-canary-r1\`.
It is intentionally persistent; do not clean it up, retry or re-use it.
A network failure after CREATE may have spent the one-shot, and the
correct response is read-only investigation, not another run.

The sequence is:
1. Confirm fixed ref is absent; only an **atomic create request** makes
   the claim. Require HTTP 201 with matching ref and source SHA.
2. Require duplicate POST to return HTTP 422.
3. Require ordinary PATCH to a different existing commit to be denied
   with HTTP 403 or 422.
4. Require force PATCH to the different commit to be denied.
5. Require DELETE to be denied.
6. GET the exact original ref and verify that original SHA persists
   after each negative probe.

If an update or delete **unexpectedly succeeds**, this is a security
incident: immediately stop and report NO-GO. The script never retries a
mutating request, never attempts remediation or cleanup, never changes
Rulesets or main, and never calls a model or device.

The GitHub artifact contains sanitized observation/report metadata only;
a successful canary still sets \`runtime_enabled=false\`,
\`codex_executed=false\` and \`hardware_verified=false\`.
It explicitly reports
\`token_identity_fully_qualified=false\` and
\`workflow_trigger_effects_audited=false\`; those require independent
inspection after a real run. A passing Actions status by itself does
**not** automatically activate Software-only Dispatch.

### Negative tests

\`\`\`bash
python3 scripts/tests/test_plasma_engineering_claim_canary.py
\`\`\`

Tests inject an in-memory protected GitHub transport (no real token,
network, refs or hardware) to cover trusted owner comments, replay,
unexpected successful update/force/delete, ambiguous create, SHA drift,
Ruleset drift, URI/path injection and credential separation.

### Remaining operational NO-GO

Live protected claim canary has not been run or authorized for this PR.
Before invoking it, separately confirm the intended Actions token identity,
the exact permanent ref, current repo Rulesets and other potential workflow
trigger impacts. Publishing a new GitHub branch can awaken workflows when
performed using credentials other than \`GITHUB_TOKEN\`; do not silently
substitute a PAT or GitHub App token.

Even after a successful real canary, a genuine software-only Codex
Worker must prove hosted disposable OS/device isolation and no GitHub
write credentials in the model process. The trusted publisher must
independently validate a real pinned patch and tests, create a scoped PR
and stop at explicit human Gate 2. The capabilities policy remains
\`runtime_enabled=false\`, and all legacy HIL workflows are unchanged.

## Two-gate checkpoint

Gate 1: review code, test offline, raise a dedicated PR; do not merge.
Gate 2: only with explicit owner approval, merge this code to main.
No GitHub ref canary, live Codex, credential provisioning, SWPC/Z2/LA2016,
FPGA, USB Hub, DUT or deployment is authorized merely by a PR merge.

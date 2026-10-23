# Path 3 Cross-Job Resume — Gate 1 Candidate (CPU-only)

**Status: UNMERGED candidate / real SWPC two-Job acceptance NOT_RUN.**

This change reuses Issue #981, the existing reusable runtime-dispatch Workflow,
the existing SWPC-plasma-codex Runner, trusted main dispatcher, and dynamic
Work Order. It introduces NO new workflow, runner, registry ID, hardware
capability, deployment, or additional owner approval gate.

## Exact two-Job contract

The one approved owner Issue command opts into the fixed
page-boundary-off-by-one fixture by specifying:

- execution_path = path3-codex; capability = codex-workspace
- scope = host-only; session_resume = page-boundary-off-by-one
- pr_number > 0 and an exact immutable source_sha

Job 1 (development-codex) launches a fresh real Codex CLI session under an
explicit Bubblewrap filesystem/device namespace. It requires an initially
failing page-boundary unittest, a still-failing test after the diagnosis-only
turn, and no first-turn file fix. The **test** result is expected FAIL but the
GitHub Job succeeds only if this expected failure was independently observed.

Job 2 (development-codex-resume) runs only after Job 1 successfully recorded
its expected failing test. It uses a new GitHub Actions Job, same trusted main,
the same immutable candidate SHA, and the existing Runner. It rechecks the
Work Order digest, GitHub Run ID, attempt=1, source/trusted SHA, UID/Runner,
checkout path and test hash. A mismatched, missing, unsafe or already-consumed
private Session refuses Resume; there is no automatic NEW fallback or retry.
A resumed Codex must produce the same Thread ID, pass the unchanged test and
write the exact synthetic first-turn-only challenge.

## State and evidence isolation

The private persistent SWPC state directory is owner-only (0700), its single
JSON resume record is 0600 and includes the raw Thread ID plus only the
SHA-256 of the synthetic first-turn challenge. Job 2 atomically consumes the
record before starting Codex. Codex rollouts and model authentication stay
under the private isolated Codex home; neither enters GitHub artifacts.
Public receipts expose only a Thread ID SHA-256, a bounded numeric per-turn
Token Usage, non-secret identifiers and test exit codes. Neither raw prompt,
session rollout, challenge, credential nor stderr is archived.

Bubblewrap uses explicit read-only system mounts, an isolated synthetic /dev,
and no host /sys or broad host home binding. It is a filesystem/device
boundary, NOT a proven network egress firewall. An unavailable isolation tool
or Codex credential causes fail-closed NOT_RUN/FAIL. No Z2, FPGA, USB, MMIO,
Power, DUT, real programming or physical hardware is authorized.

## Pre-merge acceptance blocker

GitHub-hosted PR tests can test candidate code and a fake Codex subprocess,
not real SWPC. Existing Issue #981 Actions always execute the Dispatcher from
trusted main. Before this unmerged feature reaches main, its new flag and
second Job are not live in the trusted Issue trigger. No ordinary owner
comment against the new PR can safely activate that candidate control path.

Gate 2 is BLOCKED until an actually approved, trusted Host-only premerge
SWPC path demonstrates real Job #1 NEW/expected unittest FAIL and Job #2
RESUME/FIX/PASS with Run/Job IDs, Thread and Challenge continuity, source
identity, Runner and workspace, both Token Usage reports, and a completed
Code Review. Do not merge merely to enable testing. If this cannot be
performed safely with the currently trusted mechanisms, report NOT_RUN and
stop within Gate 1 instead of bypassing the trust boundary.

A future exact owner Work Order must supply actual reviewed PR number and
source SHA; placeholders or synthetic testing do not authorize a real run.

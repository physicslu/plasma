# PLASMA — Codex Desktop versus Path 3 Token Usage (Development Mode)

Scope: offline, local-only, CPU-only analysis. No SWPC, Z2, DUT, GitHub dispatch,
production runtime, authentication files or network operations.

The extractor accepts one explicitly selected local rollout JSONL. It does not
scan credential stores or search message text. It ignores non-telemetry records
and only exports allowlisted numbers and identifiers. Never upload the raw
rollout JSONL, which can contain private prompts, tool outputs and credentials.

## Evidence baseline

Path 3 real run: https://github.com/physicslu/plasma/actions/runs/39768663770
- Runner: SWPC-plasma-codex; task: nine-nine-path3; 81/81 PASS.
- Receipt: codex_usage.status = reported; input_tokens = 251614;
  cached_input_tokens = 192896; output_tokens = 2664; codex_exit_code = 0.
- Scope: one Codex CLI exec run; not the entire GitHub Actions workflow.

Codex Desktop run, based on the owner's reported benchmark:
- Benchmark start: 2026-10-22T11:17:20Z.
- Benchmark end: 2026-10-22T11:18:59.994904Z.
- 81/81 PASS; ~100 seconds wall-clock including checks.
- Session ID, precise model, reasoning effort, token counts: NOT_AVAILABLE
  until the owner runs the local-only extraction and verifies the source.
- No private Codex Desktop rollout or other Mac-local data was read for this PR.

Do not attribute the difference between these runs to Dispatcher overhead:
Desktop single turn and Path 3 exec have different execution scopes, and
model/effort, initial context and timing boundaries are not established.

## Run the approved offline extractor on your own Mac

Use a PLASMA checkout containing this script and Python 3.10+.
Search filenames only; do not cat, grep transcript bodies or upload raw
sessions. The default CODEX_HOME is under the home directory.

    find "$HOME/.codex/sessions/2026/10/22" -type f -name 'rollout-*.jsonl' -print
    find "$HOME/.codex/archived_sessions" -type f -name 'rollout-*.jsonl' -print

For a custom CODEX_HOME, substitute that directory. Choose the rollout
associated with the original 9x9 Desktop benchmark; do not automatically
select the newest rollout and assume it belongs to the task.

Run from the PLASMA checkout (replace the placeholder with a **local** path):

    python3 scripts/plasma_codex_benchmark_usage.py \
      --session '/absolute/path/to/selected/rollout-...jsonl' \
      --start '2026-10-22T11:17:20Z' \
      --end '2026-10-22T11:18:59.994904Z'

For the optional comparison, first download the GitHub Artifact from
Run 39768663770 and locally extract plasma-path3-receipt.json.
Append this argument to the preceding invocation:

    --path3-receipt '/absolute/path/to/plasma-path3-receipt.json'

Use --output '/local/private/path/usage-summary.json' only if a local JSON
file is desired. Output must not already exist and must not be the input file.
The output includes only bounded numerical metrics and Session/Turn identity.
It is not a transcript, but IDs may still be sensitive: keep it local until
reviewed, and never commit the source rollout, credentials or other session data.

## Telemetry contract

The selected benchmark must identify exactly one task_started with a
matching task_complete and distinct turn_id inside the supplied UTC interval.
Multiple starts, absent completion or an aborted turn report NOT_AVAILABLE.
No user prompt text is used as a task selector.

Modern rollouts may contain one token_usage_record per model response:
- Dedupe by response_id within the completed turn.
- Reject conflicting duplicates, invalid/overflowing values, unknown IDs,
  response IDs reused across turn boundaries and invalid cached counts.
- Do not add cumulative token_count snapshots when response records exist.

Legacy rollouts may contain only event_msg token_count records:
- Treat total_token_usage as session-cumulative snapshots, not increments.
- Require the final pre-turn baseline and valid monotonically increasing
  snapshots within the completed turn. Compute one boundary difference.
- Never sum last_token_usage across update events or replayed snapshots.
- Missing prior baseline, no in-turn snapshot, reset or negative delta =>
  NOT_AVAILABLE. Do not silently substitute whole-Session counters.

Input Tokens already include Cached Input Tokens. Output Tokens already
include reasoning output; do not add reasoning tokens a second time.
Model and effort from turn_context are opportunistic; missing values remain
null. Locally recorded counts are not independently audited billing records.
Some Codex versions do not save usage events, in which case NOT_AVAILABLE
is the correct result, not zero.

Run synthetic Host-only tests:

    python3 -m pytest -q software/python/tests/test_plasma_codex_benchmark_usage.py

The existing Python and PL source tests GitHub-hosted PR workflow includes
software/python/tests. No SWPC Runner or hardware task is dispatched.

Codex upstream token usage notification schema:
https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/json/v2/ThreadTokenUsageUpdatedNotification.json

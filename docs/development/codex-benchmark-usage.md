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

Codex Direct session benchmark — **owner-reported local telemetry**, not
independently reproduced from the private rollout:
- The 9x9 CPU-only task finished with 81/81 PASS. Original task wall-clock
  measurement: 2026-10-22T11:17:20Z to 11:18:59.994904Z (~100 seconds).
- **Actual completed Turn boundary**: 2026-10-22T11:17:12.611Z to
  11:19:19.038Z (~126.427 seconds). The original ~100-second timing window
  omits these boundary events and correctly produces TURN_START_NOT_FOUND;
  use the independently established enclosing Turn window when extracting.
- Reported REPORTED metrics from 16 unique response records:
  input_tokens = 1951915; cached_input_tokens = 1927680;
  output_tokens = 6339. Non-cached input = 24235.
- Reported model = gpt-6-sol; reasoning_effort = medium. Session and Turn
  IDs were resolved locally, but are intentionally omitted from this public
  document; the private summary is not committed.
- **Execution host was Linux**. The record supports a Codex Direct session
  comparison, **not** verified Mac-native Codex Desktop runtime identity.
  Neither the private session nor its raw messages were available to this
  reviewer; arithmetic and CI can be independently checked, raw provenance
  cannot. Mark Mac Desktop identity NOT_VERIFIED rather than falsely PASS.

Comparison invariants (descriptive only):
- Desktop/Direct reported input is 7.76x the Path 3 exec input, but the
  cached proportion is 98.76% versus 76.66%.
- Non-cached input is **24235 versus 58718** (Direct versus Path 3).
  Cached input is already included in input_tokens in both environments.
- Output is 6339 versus 2664; different task/turn scopes and model settings
  prevent an objective cost or efficiency ranking.

Do not attribute either token delta to Dispatcher overhead: the Direct
completed Turn and Path 3 exec have different execution scopes, initial
context, timing, and not-yet-matched Path 3 model/effort. Pricing differs
for cached and non-cached tokens. An authenticated model/effort pair and
fresh-context A/B would be needed to attribute overhead.

## Run the approved offline extractor on the host with the rollout

Use a PLASMA checkout containing this script and Python 3.10+ on the
local host where the correct Codex rollout resides (Linux or macOS).
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
      --start '2026-10-22T11:17:12.611Z' \
      --end '2026-10-22T11:19:19.038Z'

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

# STM32 ICPN Phase 2.6.1 — ST Transport Diagnostic

**Research date:** 2026-08-29

## Decision target

Phase 2.6.1 isolates the transport failure observed during the first authoritative live STM32F1 pilot run. It does not change commercial ICPN evidence, parser behavior, canonical mapping, OpenOCD capability, or dataset admission.

The question is deliberately narrow:

> On a GitHub-hosted runner, which layer fails between DNS, TCP, TLS, curl HTTP, and the repository's production `urllib` acquisition path when contacting the official ST product page?

The diagnostic uses one fixed control target only:

- base device: `STM32F100C8`
- source: `https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html`

No family sweep is allowed in this phase.

## Triggering evidence

GitHub Actions run `33249021352`, attempt `1`, executed commit:

`067e4d18e9396881e38a9f24f6d7ec519fba3d39`

The uploaded artifact was:

`stm32f1-live-pilot-33249021352-1.zip`

Artifact SHA-256 recorded by GitHub Actions and independently reproduced from the downloaded artifact:

`b795c425b59c6970efdf3d560c85cf42fa26f99ab9e40ad5a7784f4426258375`

The live pilot result was:

```text
attempted                     6
acquisition_success           0
acquisition_failure           6
canonical_mapping.unique      6
canonical_mapping.ambiguous   0
canonical_mapping.unmapped    0
OpenOCD CFG mapping           6 / 6
exact_icpn_candidates         0
manual_intervention_required  6
transport evidence            0 / 6
final decision                manual_review_required
scale_ready                   false
```

All six acquisition failures reported the same error:

`The read operation timed out`

The runner used a 30-second HTTP timeout and a two-second inter-request delay. The acquisition step lasted approximately 190 seconds, which is consistent with six full read timeouts plus five inter-request delays.

## Evidence interpretation

The run does **not** show that ST removed the expected 26 candidate ICPNs.

`observed_exact_icpn_candidates = 0` occurred because no product page response completed successfully. Therefore:

- `candidate_baseline_match = false` is transport-unavailable evidence, not commercial-part-number drift evidence;
- `candidate_drift = []` does not establish equality or inequality with the 26-candidate baseline;
- parser correctness was not exercised against a completed live response;
- canonical and OpenOCD mapping remained independently clean at 6/6.

The current fault domain is therefore the live HTTP transport path, not the commercial ICPN dataset or canonical device mapping.

## Diagnostic architecture

The checked-in diagnostic is `diagnose_st_transport.py`.

It executes this sequence:

```text
single fixed ST target
        |
        +--> DNS resolution
        +--> TCP connect :443
        +--> TLS handshake
        |
        v
repository urllib acquisition path
        |
        +-- success --> transport_ok; stop HTTP diagnostics
        |
        +-- failure
              |
              +--> wait >= 1 s (default 2 s)
              +--> curl with the same Plasma User-Agent + Accept headers
                    |
                    +-- success --> urllib_specific_failure
                    |
                    +-- failure
                          |
                          +--> wait >= 1 s (default 2 s)
                          +--> curl default request profile
```

The curl comparisons run only after the real `urllib` production path fails. This keeps the normal successful preflight to one HTTP GET and bounds the failure diagnostic to one target.

## Classification contract

The diagnostic emits one conservative classification:

| Classification | Interpretation |
|---|---|
| `transport_ok` | The repository `urllib` production path completed successfully. |
| `urllib_specific_failure` | curl with the same Plasma request headers succeeds while `urllib` fails; investigate Python/urllib/TLS/HTTP-stack behavior. |
| `request_header_policy_suspected` | curl default succeeds while curl with Plasma headers and `urllib` fail; request-header/WAF policy becomes a primary hypothesis, not a proven cause. |
| `dns_failure` | DNS resolution itself fails. |
| `tcp_path_failure_or_address_selection` | TCP probe fails after DNS; address-family/path selection needs review. |
| `tls_path_failure_or_address_selection` | TLS probe fails; certificate/TLS/address-path behavior needs review. |
| `upstream_http_response_failure_or_filter` | DNS/TCP/TLS complete, but `urllib` and both curl profiles fail; GitHub-runner-to-ST HTTP response path, CDN/WAF behavior, or upstream filtering becomes the primary fault domain. |

The wording is intentionally cautious. The diagnostic identifies the next fault domain; it does not claim to prove ST policy or CDN internals from one run.

## Live-pilot workflow change

The existing manual-only workflow remains `STM32F1 live acquisition pilot` and remains triggered only by `workflow_dispatch`.

Before the six-target pilot it now runs the single-target transport diagnostic. If the production `urllib` preflight fails:

1. diagnostic JSON is still uploaded;
2. the six-target acquisition is skipped;
3. the workflow fails closed;
4. the run does not spend another ~190 seconds repeating six known-bad requests.

If `urllib` preflight succeeds, the normal six-target Phase 2.6 live pilot proceeds unchanged.

## Deterministic CI boundary

Normal pull-request CI remains offline with respect to `st.com`.

CI validates:

- transport classification logic;
- urllib-success short circuit;
- curl escalation order after urllib failure;
- minimum one-second request spacing;
- the fixed single-target boundary;
- manual-only workflow trigger;
- preflight-before-six-target workflow ordering and fail-closed behavior.

CI does not claim that DNS, TLS, curl, or urllib succeed against ST at CI execution time.

## Scope exclusions

Phase 2.6.1 does not:

- change the 26-candidate research baseline;
- admit any commercial ICPN into `stm32f1-commercial-icpn.csv`;
- alter the Phase 2.4 parser to accommodate a timeout;
- increase the Phase 2.6 live timeout as a substitute for diagnosis;
- sweep additional STM32F1 devices;
- change production Plasma runtime, Web UI/API, deployment, FPGA/Z2, or real-IC behavior.

## Exit criteria

The next action depends on one measured diagnostic classification, not speculation:

- `transport_ok`: rerun the six-target live pilot and evaluate the authoritative evidence;
- `urllib_specific_failure`: repair or replace the Python transport layer under a separately reviewed change;
- `request_header_policy_suspected`: isolate request-header behavior before changing transport;
- lower-layer failure: investigate the corresponding DNS/TCP/TLS path;
- `upstream_http_response_failure_or_filter`: stop treating GitHub-hosted Actions as an assumed-valid ST acquisition environment and compare against another controlled execution environment such as Codex or the integration host before selecting the long-term acquisition runner.

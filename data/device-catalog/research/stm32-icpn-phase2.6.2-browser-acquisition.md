# STM32 ICPN Phase 2.6.2 — Browser-backed ST acquisition

## Decision

Phase 2.6.2 moves live ST product-page acquisition away from raw HTTP clients and away from GitHub-hosted execution.

Observed Phase 2.6 / 2.6.1 evidence showed the same failure boundary in two independent environments:

- GitHub-hosted Ubuntu runner: DNS/TCP/TLS succeeded; urllib timed out; curl HTTP/2 failed with `INTERNAL_ERROR`.
- Codex macOS execution: DNS/TCP/TLS succeeded; urllib timed out; curl HTTP/2 failed with the same `INTERNAL_ERROR`.

This does **not** prove that ST blocks every raw HTTP client permanently. It is sufficient to conclude that the observed raw HTTP path does not meet Plasma's reliability requirement for authoritative ICPN acquisition.

## Architecture

```text
ST official product page
        |
        v
real Chromium browser (Playwright)
        |
        v
rendered DOM
        |
        v
existing Quality & Reliability / Part Number parser
        |
        v
transport-explicit provenance evidence
        |
        v
existing candidate baseline + mapping evaluator
```

The browser adapter is intentionally separate from `fetch_html()`. Raw HTTP remains a distinct transport and retains its original evidence semantics.

## Evidence semantics

Browser-rendered evidence must never claim to be raw HTTP evidence.

Raw HTTP evidence:

- `raw_sha256`
- optional `ETag`
- optional `Last-Modified`

Browser evidence:

- `acquisition_transport = chromium_rendered_dom`
- `rendered_dom_sha256`
- `evidence_section_sha256`
- no `raw_sha256` claim
- no raw HTTP cache-header claim

Both paths still require:

- approved canonical `https://www.st.com/en/...html` source/final URL
- retrieval timestamp
- `quality_and_reliability_part_number` evidence surface
- exact commercial ICPN candidates
- fail-closed mapping/evaluation
- no canonical dataset admission during research acquisition

## Runtime boundary

Playwright is a research-only live-acquisition dependency:

```bash
python -m pip install -r data/device-catalog/research/requirements-st-browser.txt
python -m playwright install chromium
```

It is not added to Plasma Server, Web Gateway, Web Console, PPU runtime, FPGA, or deployment dependencies.

## Controlled execution sequence

Live execution is performed by Codex in its execution environment, not by GitHub Actions.

### Step 1 — control target only

```bash
python data/device-catalog/research/run_stm32f1_browser_pilot.py \
  --scope control \
  --delay 2.0 \
  --timeout 30 \
  --output /tmp/stm32f1-browser-control.json
```

The control target is fixed to `STM32F100C8`.

The run must fail closed if:

- navigation redirects outside approved ST product URLs
- browser navigation returns HTTP error
- Quality and Reliability is not visible
- Part Number is not visible
- a CAPTCHA/access-denied/challenge marker is visible
- the rendered DOM exceeds the bounded response limit
- exact commercial candidates cannot be extracted
- canonical/OpenOCD mapping is not executable

Expected control candidates from the checked-in Phase 2.5 research baseline:

- `STM32F100C8T6B`
- `STM32F100C8T6BTR`
- `STM32F100C8T7B`
- `STM32F100C8T7BTR`

### Step 2 — six-target pilot

Only after Step 1 succeeds:

```bash
python data/device-catalog/research/run_stm32f1_browser_pilot.py \
  --scope pilot \
  --delay 2.0 \
  --timeout 30 \
  --output /tmp/stm32f1-browser-pilot.json
```

The existing six-target manifest remains authoritative for the bounded pilot.

### Step 3 — scale-readiness evaluation

```bash
python data/device-catalog/research/evaluate_stm32f1_live_pilot.py \
  --summary /tmp/stm32f1-browser-pilot.json \
  --output /tmp/stm32f1-browser-evaluation.json \
  --repository physicslu/plasma \
  --git-sha "$(git rev-parse HEAD)"
```

A clean result still requires:

- attempted = 6
- acquisition success = 6
- acquisition failure = 0
- canonical mapping = unique 6 / ambiguous 0 / unmapped 0
- OpenOCD CFG mapping = 6 / 6
- manual intervention = 0
- 6 / 6 valid transport-specific provenance records
- exact candidate count = 26
- exact candidate set matches the Phase 2.5 baseline, not merely the count
- `scale_ready = true`
- `canonical_dataset_admission = false`

## Prohibited behavior

This phase does not:

- bypass CAPTCHA or WAF controls
- add browser-impersonation headers to raw HTTP clients
- retry until a desired result appears
- change the 26-candidate baseline to force a pass
- write `stm32f1-commercial-icpn.csv`
- sweep the remaining STM32F1 inventory
- deploy Plasma
- restart services
- operate FPGA/Z2/real IC hardware

## CI policy

Normal pull-request CI validates the browser acquisition contract with deterministic fake-page tests. It does not install Chromium and does not contact `st.com`.

Live manufacturer acquisition remains an explicit research execution performed by Codex after the code path is reviewed and merged.

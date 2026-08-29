# STM32 ICPN Phase 2.4 — authoritative source acquisition architecture

**Research date:** 2026-08-29

## Executive decision

Plasma should stop treating manual page-by-page transcription as the scale-out mechanism for STM32 commercial ICPNs.

For the next stage, the primary commercial-identity acquisition surface is the canonical `www.st.com` product page for a base device. On the representative STM32F103C8, STM32F103CB, STM32F103RB, and STM32F103RE pages, ST renders a `Quality and Reliability` section containing a `Part Number` table with the exact commercial order codes. This evidence is present in the product-page HTML independently of the JavaScript-heavy `Sample & Buy` presentation.

No documented ST bulk JSON/CSV/catalog API for exact commercial STM32 order codes was established in this research pass. This is deliberately an evidence statement, not a claim that ST has no private/internal endpoint.

Therefore Phase 2.4 adopts a **source-page acquisition + fail-closed extraction + provenance digest** architecture. It does not add new ICPNs and it does not automatically promote extracted candidates into the canonical commercial dataset.

## Evidence observed on representative official pages

The following canonical ST product pages were inspected:

- <https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html>
- <https://www.st.com/en/microcontrollers-microprocessors/stm32f103cb.html>
- <https://www.st.com/en/microcontrollers-microprocessors/stm32f103rb.html>
- <https://www.st.com/en/microcontrollers-microprocessors/stm32f103re.html>

Across all four pages, the `Quality and Reliability` section exposes an explicit `Part Number` table. The table reproduces the exact ICPNs already admitted in the checked-in Phase 2 dataset for those four base devices.

This is a stronger acquisition surface than deriving combinations from datasheet ordering grammar because each candidate string is emitted directly by ST for that product page.

### Surfaces that remain secondary

- **ST eStore:** useful corroboration for package, temperature, stock and commercial context, but inventory and price are volatile and should not be the stable primary extraction surface.
- **ST datasheets:** authoritative for field semantics of an already-proven exact code, but not proof that every syntactically possible code is commercially available.
- **STM32CubeMX / CMSIS databases:** useful for firmware/base-device identity. They are not exact commercial-order-code authority. No undocumented CubeMX database format should be elevated into commercial identity ground truth.
- **OpenOCD:** programming-capability evidence only.

## Acquisition pipeline

```text
base-device source manifest
        |
        | canonical https://www.st.com/.../<base>.html
        v
bounded HTTP acquisition
        |
        +--> final URL / status / content type
        +--> retrieval timestamp
        +--> ETag / Last-Modified when present
        +--> SHA-256(raw response bytes)
        v
fail-closed HTML extraction
        |
        | locate: Quality and Reliability
        | require: Part Number surface
        | accept: exact STM32* tokens matching requested base
        v
candidate evidence record
        |
        +--> parser/schema version
        +--> normalized evidence-section SHA-256
        +--> exact candidate ICPN list
        +--> source URL and retrieval metadata
        v
human/agent evidence review
        |
        +--> applicable official datasheet field semantics
        +--> CMSIS/base identity
        +--> unique Plasma canonical mapping
        +--> OpenOCD target capability
        v
checked-in commercial ICPN dataset
```

The acquisition stage and dataset-admission stage are intentionally separate. A web parser finding a token is not by itself enough to modify `stm32f1-commercial-icpn.csv`.

## Fail-closed requirements

The acquisition probe must reject or stop when any of these conditions is true:

1. Source URL is not HTTPS on the approved ST product host.
2. Redirect leaves the approved ST host.
3. HTTP response is not successful HTML or exceeds the bounded response size.
4. `Quality and Reliability` cannot be located.
5. A `Part Number` marker is absent from that section.
6. No exact ICPN matching the requested base device is present.
7. The section contains an unexpected foreign STM32 device token.
8. Candidate strings are duplicated only after inconsistent normalization or otherwise fail lexical checks.
9. Parser/schema version is unknown to the consumer.

A site-layout change must produce a visible failure, not an empty-success result.

## Provenance record

A candidate acquisition record should contain at least:

```json
{
  "schema_version": 1,
  "parser_version": 1,
  "source_url": "https://www.st.com/.../stm32f103rb.html",
  "final_url": "https://www.st.com/.../stm32f103rb.html",
  "base_device": "STM32F103RB",
  "retrieved_at_utc": "<ISO-8601>",
  "http_etag": "<optional>",
  "http_last_modified": "<optional>",
  "raw_sha256": "<sha256 of acquired HTML bytes>",
  "evidence_section_sha256": "<sha256 of normalized evidence text>",
  "evidence_surface": "quality_and_reliability_part_number",
  "exact_icpns": ["..."]
}
```

The raw response digest proves exactly which byte stream was parsed. The normalized section digest makes meaningful evidence-surface changes easier to detect.

### Why the full HTML is not committed by default

Full ST pages are large, contain volatile presentation/commerce data and are not a good Git source format. Phase 2.4 therefore records hashes and extracted facts rather than copying full web pages into the repository.

This is an audit mechanism, not full offline replay. If regulatory or long-term reproducibility later requires byte-for-byte replay, store the raw acquisition body in a controlled artifact/object store keyed by `raw_sha256`, with legal/retention policy explicitly defined. Do not silently turn the Git repository into a third-party web archive.

## Deterministic CI boundary

Normal pull-request CI must not depend on live `st.com` availability. External network state, rate limiting, maintenance windows and content rollout timing are not properties of a Plasma commit.

CI should instead test the extraction logic against synthetic local HTML fixtures and continue validating the checked-in commercial dataset with the existing fail-closed validator.

A future freshness monitor, if desired, should be a separate scheduled research workflow whose failure does not make unrelated production PRs red. Any detected source drift should create a reviewable evidence change; it must never rewrite the commercial ICPN dataset automatically.

## Operational constraints

- Fetch sequentially or with very low concurrency; do not aggressively crawl ST infrastructure.
- Cache/reuse recently acquired source evidence when doing research sweeps.
- Keep pricing, stock and distributor availability out of the commercial identity model.
- Never generate missing order codes from grammar to fill perceived gaps.
- Never promote a candidate to verified commercial ICPN unless the exact string is present in authoritative ST evidence and downstream identity mapping is deterministic or explicitly classified otherwise.

## Scale-out decision

The next scalable unit is no longer “manually research another MCU.” It is:

```text
manifest of known STM32 base-device product URLs
    -> reproducible candidate extraction
    -> provenance review
    -> datasheet decoder by applicable document family
    -> deterministic mapping validator
```

Only after this acquisition path is proven on additional heterogeneous STM32F1 product groups should Plasma consider a broader family sweep. The current 23 exact ICPNs remain the authoritative checked-in dataset; Phase 2.4 itself adds zero commercial ICPNs.

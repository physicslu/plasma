# ST eStore Whole-STM32 Active Exact Coverage v1.3

**Research-only Catalog audit. No PS/backend/HIL work and no Production write.**

## Why this gate changes the coverage question

The official ST eStore exposes four parent STM32 MCU categories that partition the scoped MCU/wireless portfolio:

| Official eStore parent category | Current observed Marketing Status facet |
| --- | ---: |
| STM32 Mainstream MCUs | Active 1,807; NRND 6 |
| STM32 High Performance MCUs | Active 1,127; NRND 25 |
| STM32 Ultra Low Power MCUs | Active 1,371; NRND 4 |
| STM32 Wireless MCUs | Active 245 |
| **Total observed Active** | **4,550** |
| **Total observed NRND** | **35** |

The parent-category subcategory counts independently reconcile to \`Active + NRND\`, and the four top-level categories are distinct. These public surfaces therefore provide a much stronger candidate denominator than the former manufacturer marketing statement of “more than 4,500 commercial part numbers.”

The v1.3 workflow does **not trust the above counts as constants**. Each matrix job discovers its current pagination and Marketing Status facets live, then exhaustively reads every product card. Every card must contain exactly one exact \`STM32...\` commercial identity and exactly one recognized \`Active\` or \`NRND\` state. The final observed card counts must reconcile exactly to the live manufacturer facets.

## Exact set math

After all four independent segment acquisitions succeed, the reconciliation job computes:

\`\`\`text
A = official eStore current Active exact STM32 MPN set
P = frozen Plasma Production ST exact ICPN set (2,683)

Catalog Active Coverage = |P ∩ A| / |A|
Missing Catalog candidates = A - P
Production not currently Active = P - A

Production not currently Active is further split into:
  P ∩ official eStore NRND
  P - (Active ∪ NRND)    # lifecycle must NOT be inferred without Q&R recheck
\`\`\`

This is materially better than \`2683 / 4550\`: some Production records may now be NRND or absent from the eStore surface, so only the exact intersection belongs in the numerator.

## Evidence and trust boundary

- Raw HTML for every page is written before interpretation and retained as 30-day GitHub Actions artifacts.
- Per-page SHA-256, source URL and capture timestamp are retained.
- Each top-level segment is acquired independently in parallel to reduce time and isolate source failures.
- The final result includes the complete Active exact set, missing-Production set, Production-current-Active intersection, Production-NRND set and unresolved Production-not-eStore-listed set.
- An eStore Active exact identity is a **Catalog identity candidate**. It is not Programming Backend/Profile support, Engineering Verified status or Production field evidence.
- An identity absent from eStore is not automatically Obsolete; Quality & Reliability must resolve lifecycle before removing or downgrading an existing Catalog row.
- Publication of any new exact ICPN remains a separate explicit owner-approval transaction.

If the exhaustive page set reproduces the live facets without collision, this gate establishes an official-eStore Active exact coverage KPI for the scoped STM32 MCU/wireless portfolio.

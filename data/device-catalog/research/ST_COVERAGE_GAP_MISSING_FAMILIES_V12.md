# ST Coverage Gap v1.2 — Missing-family Active Exact-MPN Acquisition

**Research-only. No Production Catalog write.**

This gate extends the frozen ST Production baseline of **2,683 exact ICPNs / 23 families** and the already evidence-locked **172 STM32C5 Active exact MPNs**.

It deliberately ignores PS/OpenOCD readiness. The question is narrower:

> Which exact, currently Active manufacturer ordering codes are absent from the Device Catalog because their entire STM32 family is not represented in Production?

## Live official sources

The acquisition uses only official ST-controlled public surfaces:

- STM32H5: complete ST eStore family category, all pages, Active facet and exact product cards.
- STM32N6: complete ST eStore family category.
- STM32WB0: complete ST eStore family category.
- STM32WL3: ST official product selector frozen to the 14 currently exposed Base Devices, followed by each Base Device's Quality & Reliability table.
- STM32C5: reuses the existing v0.7 raw-evidence-locked 172-exact set rather than reacquiring it here.

The eStore collector **discovers** the current page count and Active facet from the first manufacturer page and then requires every page/card to reconcile exactly to that facet. It does not hard-code 185/32/24 merely because those counts were observed during design.

The WL3 collector fails closed unless the selector exposes exactly this currently reviewed Base Device set:

```text
STM32WL3RK8  STM32WL3RKB
STM32WL30K8  STM32WL30KB
STM32WL31K8  STM32WL31KB  STM32WL31C8  STM32WL31CB
STM32WL33K8  STM32WL33KB  STM32WL33KC
STM32WL33C8  STM32WL33CB  STM32WL33CC
```

Every retained WL3 commercial identity must appear in an official Quality & Reliability row with `Active Product is in volume production`.

## Evidence boundary

This acquisition is intended to establish a **complete missing-family Active exact cohort for the five currently absent STM32 families**, subject to successful final-head CI and review of the retained raw manufacturer bytes.

It still does **not** establish whole-ST coverage because it does not yet re-audit missing exact variants inside the existing 23 Production families.

Therefore the derived quantity

```text
2683 / (2683 + confirmed missing-family Active exact MPNs)
```

is a **confirmed-set inventory coverage ratio**, not the final whole-ST Active Coverage Rate.

After this gate, the next work item is the more expensive one: re-enumerate the current official Active exact MPNs within the existing 23 Production families and compute their set difference against the frozen 2,683.

No collected identity is automatically publishable. Catalog publication remains a separate explicit owner-approval transaction.

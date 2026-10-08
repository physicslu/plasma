# OpenOCD Tier A Bounded Suffix-Normalization Proposal v6.13

Research-only policy proposal for the **33** Tier A identities that v6.7 resolves uniquely after removing the Catalog's already-authoritative `option_suffix`.

## Decision

Do **not** authorize a family-wide or generic suffix-removal rule.

Instead, freeze an exact-set bridge:

- exact identities: **33**
- each ICPN retains its full commercial identity;
- normalization is used only as a routing bridge;
- each row must resolve to exactly one existing OpenOCD identifier and target config;
- identities outside the frozen set remain fail-closed.

This proposal does not modify Production and does not change manufacturer metadata.

## Why bounded

v6.7 proves uniqueness only for the observed 33 identities. It does not prove that every current or future suffix-bearing STM32 identity may safely remove the same suffix for OpenOCD routing.

The v6.13 bridge therefore records the exact ICPN, authoritative Catalog option suffix, normalized routing core, identifier kind, existing identifier, and target config for each admitted candidate.

## Coverage implication

If the original **320** v6.5 identifier-qualified identities plus these **33** bounded suffix-normalization candidates later pass a separate backend-promotion transaction:

**3,947 / 4,550 = 86.7473%**

Remaining Active route gap: **603**.

The separate v6.12 C0 bounded bridge is intentionally not folded into this policy. A later consolidated promotion proposal may combine independently frozen policies.

No erase/program/verify, Programming Profile, Engineering Verified, or HIL claim is made.

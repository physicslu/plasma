# OpenOCD Tier A Blocked Classification v6.6

This research pass classifies the **69** v6.5 Tier A identities that did not resolve to one policy-compatible identifier.

The purpose is diagnostic only. It does not manufacture identifiers or change Production mappings.

Each blocked identity is assigned to one structural class:

1. **same-base route inventory present, but no policy match** — OpenOCD evidence knows the base-device neighborhood, but the exact commercial core does not match an admitted identifier pattern.
2. **same-series route inventory present, but base variant absent** — the series exists in route evidence, but this base-device shape is not represented.
3. **no same-series route inventory row** — target config is known from Production siblings, but the canonical route inventory lacks the series evidence needed to resolve this candidate.

The output also preserves option-suffix distribution so suffix-specific gaps can be separated from package/flash/base-device gaps.

No blocked row is promoted by v6.6.

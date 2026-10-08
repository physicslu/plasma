# OpenOCD STM32C0 Bounded Identifier Bridge Proposal v6.12

Research policy proposal for the **11** STM32C0 residual identities that v6.11 resolved uniquely.

## Decision

Do **not** authorize a generic one-character-generalization rule for STM32C0.

Instead, freeze an exact-set bridge:

- exact identities: **11**
- target config: `tcl/target/stm32c0x.cfg`
- identifier kind: `ordering_pattern`
- each exact ICPN maps to one specific existing OpenOCD route identifier
- no identity outside the frozen 11-row set may use this bridge

Examples:

- `STM32C051K8U3` → `STM32C051K8Tx`
- `STM32C071FBY6TR` → `STM32C071FBPx`
- `STM32C091RBI6` → `STM32C091RBTx`

## Why bounded instead of generic

The v6.11 probe proves uniqueness only for these 11 identities. It does not prove that a family-wide one-character rule is semantically valid for future or unseen STM32C0 variants.

The bounded bridge therefore preserves fail-closed behavior.

## Coverage implication

This is still only a proposal. Production remains unchanged.

If the existing 353 qualified/normalizable Tier A identities plus these 11 bounded C0 bridges later pass a separate promotion transaction:

**3,958 / 4,550 = 86.9890%**

Remaining Active route gap: **592**.

This does not establish erase/program/verify or HIL success.

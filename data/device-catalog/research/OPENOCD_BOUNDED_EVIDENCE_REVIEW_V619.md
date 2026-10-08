# OpenOCD Exact-Set Bounded Evidence Review v6.19

Research-only evidence review for the **17 exact ICPNs** that v6.18 resolved uniquely only under the one-character diagnostic.

## Decision model

This review follows the governance precedent used by the earlier STM32C0 bounded bridge:

- do **not** authorize a generic one-character normalization rule;
- freeze only the exact ICPNs that currently resolve uniquely;
- bind each exact ICPN to one existing upstream OpenOCD identifier candidate and one target config;
- keep route validation at `not_verified`;
- keep Programming Profile, erase/program/verify, Engineering Verified, and HIL claims unresolved.

## Evidence chain

For every reviewed row, v6.19 requires:

1. a verified Production commercial identity whose source authority is official ST;
2. a non-empty retained ST source reference;
3. one unique candidate from the frozen upstream OpenOCD route inventory under the v6.18 diagnostic;
4. exact preservation of the v6.18 evidence digests and OpenOCD route-inventory Git blob.

The result is an **exact-set bridge candidate**, not a Production mapping.

If all 17 candidates later pass a separately approved bounded-bridge proposal and Production transaction, Active route coverage would move from **3,958 / 4,550 = 86.9890%** to **3,975 / 4,550 = 87.3626%**, leaving **575** route gaps.

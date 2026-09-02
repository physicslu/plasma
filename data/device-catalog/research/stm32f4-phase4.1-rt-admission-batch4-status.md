# STM32F4 Phase 4.1 R/T Batch4 status

Status: discovery pending.

Bounded scope:
- lifecycle control: `STM32F479ZG`
- admission targets: `STM32F446RC`, `STM32F446RE`
- pilot target count: 3
- canonical admission: disabled during discovery

Safety gates:
- official ST browser evidence only
- exact ICPNs are not inferred
- non-Active observations remain audit-only
- one whole-batch retry maximum after a dirty discovery attempt
- no Production write before retained evidence, drift-free baseline evaluation, read-only proposal, and controlled publish

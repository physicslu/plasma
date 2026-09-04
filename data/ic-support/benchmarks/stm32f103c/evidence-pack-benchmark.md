# Evidence Pack benchmark note

The STM32F103C Evidence Pack A/B experiment is deliberately separate from the existing formal blind extraction benchmark.

- Formal blind benchmark authority remains `source-lock.json` and its existing extraction contract.
- Manufacturer-only A/B compares the same model/runtime/prompt against:
  - full DS5319 + full PM0075;
  - deterministic DS5319 Evidence Pack + full PM0075.
- The Plasma STM32F1 catalog blob remains part of the formal blind benchmark but is not injected into the manufacturer-only A/B arm merely to make the experiments look identical.
- Raw model outputs must remain immutable experiment evidence.
- Reduced context is acceptable only if required evidence recall and engineering correctness do not regress.

See `evidence-pack-benchmark-v0.json` for the machine-readable experiment contract.

# Open Provider Framework — Gate 1 Host-only contract

**Owner scope:** 2026-11-04 Open Provider Framework Gate 1, grounded in the
[Unified Bundle-driven Programming Decision](unified-bundle-driven-programming-decision-2026-11-04.md).
Engineering and Production share the same PPU execution path. Console policy
remains separate. This contract does not authorize Z2 deployment or DUT work.

## Vertical slice

One verified Bundle v3 is one Active Asset Set. A data Package may contain
`data/plasma-provider.json` using `plasma.ppu.provider-capabilities.v1`. Its
`provider_package` names a `python` or `native-c` Package in the same Bundle;
the data Package must declare that Package in `requires`. An FPGA transport
also requires one `fpga-image` Package in the same Bundle. The Provider's
entrypoint is a verified Package file, not an executable instruction from the
descriptor. Bundle install and Active Set activation remain separate.

The descriptor has exactly these fields: `schema`, `target`,
`provider_package`, `operations`, `sites`, `transport`, `driver_abi`,
`fpga_package`, `max_image_bytes`. Operations are drawn from
`erase`, `program`, `verify`, `read`, `flash_cycle`; a requested operation must
be present. `transport` is `fpga` or `ps-only`. Capability strings and Package
IDs are Bundle data, never Core allowlist entries. `flash_cycle` still requires
independent complete-cycle evidence from the executor; advertising it alone
does not prove it. The descriptor is not a Job, authority to execute a Package,
or authority to access Root, MMIO or the DUT.

Job execution time is governed by a **single** OPF `timeout_ms` selection
(PPU default, or Bundle override within a PPU safety ceiling); the Provider
capability descriptor does not define an independent runtime timeout. See
[OPF-1 architecture / single-timeout proposal — Draft PR #1302](https://github.com/physicslu/plasma/pull/1302).
The two Draft PRs remain independently reviewed until coordinated integration.

Host-only `ppu_provider_contract.resolve` independently re-verifies the Active
Set, binds its ZIP SHA, exact target, operation, Site, image size, Provider and
Profile Package, and compares Bundle target and declared transport against a
trusted device-side capability observation. FPGA use additionally requires
proven loaded image and matching Driver ABI at the point of use. No source-tree
fallback, Catalog lookup, ICPN registry, fixed OpenOCD engine or fixed Image
ID participates in this resolution. The runtime must supply the hardware
observation; an HTTP or Bundle field must never be used as that observation.

## Core safety boundary for Runtime integration

The Runtime owns Job authorization and Active Set pinning, Site ownership,
lease and lock, bounded execution, cancellation, SAFE_OFF, Recovery and
unknown-outcome sealing. A Provider cannot grant itself any of these. Use the
existing Site Worker and Asset Execution owner controls when wiring the
resolved route to an executor. A changed FPGA identity or unknown SAFE_OFF is
an uncertain outcome, never a successful retry. A valid Bundle digest alone
does not establish Publisher/Owner trust or actual hardware readiness.

This initial interface change is Host-only. It proves route resolution and
fail-closed checks with a reference-style FPGA route and an independent
PS-only route. Provider process execution, the REST Runtime integration and
physical compatibility remain NOT_RUN until their separate integration and
hardware acceptance work.

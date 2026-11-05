# OPF-3B — Provider Route / Site Session / Job timeout integration

**Status:** Host-only integration. Production Runtime Flash dispatch remains on
the existing C-3 route. No Provider process execution or hardware acceptance
is claimed.

The trusted Runtime parses the OPF-1 selection with PPU timeout policy, then
calls the existing `ppu_provider_contract.resolve` against the selected,
verified Active Asset Set and a device-side hardware observation. The
`ppu_opf_site_session.open_provider_job_session` helper carries that exact
resolved route to the existing C-3 `open_job_session` control operation. Only
the trusted Runtime peer can issue it. The Site Worker holds an immutable copy
of the Active Set digest, Provider, Profile, descriptor and options digests,
Driver/FPGA binding, operation and Site in its existing per-Site Session.
Subsequent `run` calls must use the bound Site and operation. The existing
Job lease, Site owner, hardware identity fence, external owner check, Site
lock, SAFE_OFF and persistent unknown-outcome seal still apply.

The OPF-1 effective `timeout_ms` must equal the PPU Job request's timeout.
`SiteWorker._process` snapshots one monotonic deadline when a Job starts and
applies the remaining budget to attempts and retry backoff. The OPF session
receives that same absolute deadline. Its integer `max_runtime_s` is only an
admission ceiling. Expiry or cancellation does not clear a seal or declare
SAFE_OFF. A proven safe OpenOCD/Flash failure is a Job failure eligible for
PPU retry policy; an unknown hardware state remains sealed until the existing
authorized recovery procedure.

This integration does not accept a client supplied hardware observation,
switch the production Flash executor, install a Provider, reload FPGA, or
change the native SWD driver/OpenOCD binary. The host tests exercise route
identity, ownership, timeout, cancellation, restart, safe failure and unknown
outcome using simulated adapters. Z2, FPGA and DUT acceptance is **NOT_RUN**.

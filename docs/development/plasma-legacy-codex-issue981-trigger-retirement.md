# PLASMA — Issue #981 Legacy Codex Trigger Retirement (historical record)

The original change removed issue_comment trigger registration from nine historical workflows. This decision predates the 2026-10-26 Path 3 direct-tools consolidation and is **not** a current operational entrypoint.

## Current status

- The active engineer route is the shared trusted-main `.github/workflows/plasma-engineering-runtime-dispatch.yml`, `scripts/plasma_development_dispatch.py` and [Path 3 Direct Hardware Tools](plasma-path3-direct-hardware-tools.md).
- The three retired LA2016-specific workflows `plasma-codex-la2016.yml`, `plasma-codex-la2016-direct.yml`, `plasma-codex-la2016-diagnose.yml`, their JSON Host Supervisor/LA-only launcher/diagnostics and related scenario tests have been removed. Former exact Issue commands are not supported or automatically remapped.
- The six other historical Issue #981 workflows remain dormant, without issue_comment trigger registration.
- Retain verified KINGST AppImage provenance, original 2026-10-16 waveform archive, 2026-10-23 SWD reference, private Z2 SSH credentials, actual FPGA Root Guard/Manifest, hardware mutex, and Z2 PS OpenOCD/WordPort.
- This source-only change neither authorizes nor performs SWPC/LA/Z2/FPGA/DUT physical operations, OS privilege changes, or deployment. Host-only tests do not prove current device access.

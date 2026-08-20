# Domain Naming and Identity Policy

Canonical Plasma product/domain hierarchy is:

```text
Facility -> PPU -> Site
```

Canonical Site identity is **one-based**:

```text
SITE 1 .. SITE N
```

There is no canonical `SITE 0`.

## Canonical v3.3 contract

- Product/UI: `PPU`, `SITE n`, `Facility`.
- Configuration: `ppu`, `facility_id`, `sites`, `max_supported_sites`, `max_queue_depth_per_site`.
- YAML `sites:` IDs are `1..N`.
- Python domain types: `PPUConfig`, `SiteConfig`, `SiteState`, `SiteManager`, `SiteWorker`.
- Python canonical modules: `plasma_server.site_manager` and `plasma_server.site_worker`.
- Plasma Server scheduling, Job state, audit logs and read-back outputs use one-based `site_id`.
- Protocol v3.3 uses `PLASMA33`, `protocol_version: "3.3"`, and one-based `site_id`.
- Protocol v3.3 STATUS exposes `ppu` and `sites` only.
- Plasma Web REST Gateway REST v3 accepts one-based `site_id` / `?site=`.
- CLI uses one-based `--site` and renders `SITE<n>`.
- Canonical Job audit logs are written under `SITE<n>` and contain `site_id` only.
- Read-back outputs use `read_SITE<n>_<section>.bin`.
- Site errors are `SITE_INVALID`, `SITE_DISABLED`, `SITE_BUSY`.

## No compatibility boundary

Plasma is still in development and has no external compatibility requirement for the retired Programmer/Channel model. The canonical runtime therefore does not maintain a second zero-based identity adapter, legacy configuration facade, alternate STATUS shape, or legacy audit mirror.

Historical Git commits and migration documents may explain how the project reached the current model. They are not executable contracts.

## Boundary rules

Current code and current guidance must not:

- create or display `SITE 0`;
- introduce a second Site identity namespace;
- expose alternate Programmer/Channel product models;
- write retired identity fields into canonical Site audit records;
- reintroduce compatibility aliases without an explicit new product requirement and versioned migration plan.

The following remain independent from this naming policy:

- stable PPU IDs;
- FPGA / PL RTL logic and physical hardware behavior;
- deployment topology;
- Python distribution identity `plasma-multichannel` until separately renamed.

## Programming data vocabulary

The same canonical-only principle applies to programming data:

```text
REST v3 input       -> Programming Asset
Execution model     -> Normalized Image
Protocol v3.3 wire  -> image_size / image_sha256 / Image payload
Per-device identity -> Serial Number Asset
```

`Firmware` is not the canonical programming-data abstraction. Programming Recipe remains a future control-plane concept and is not an Asset merely because it can be serialized as a file.

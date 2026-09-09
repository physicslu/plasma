# Control Station Managed PPU Selection

> Status: current Control Station routing contract for selecting one Manager-enrolled PPU for Managed Programming and Diagnostics.

## Problem boundary

A packaged Control Station must not require Console restart merely because the operator changes which enrolled PPU is used for Managed operations. The Plasma Gateway Endpoint remains Manager-owned registry data; the Browser never supplies an arbitrary destination URL.

The runtime path is:

```text
Browser
  -> same-origin Console/BFF
  -> selected Manager registry alias
  -> Plasma Manager
  -> Manager-resolved Plasma Gateway Endpoint
  -> PPU
```

## Ownership

- Manager runtime registry owns PPU inventory, lifecycle, and alias -> Plasma Gateway Endpoint mapping.
- Control Station/BFF owns the current operator selection of a registry alias for Managed operations.
- Browser UI may request selection of an alias, but it does not persist or receive the PPU endpoint as routing truth.
- `PLASMA_MANAGER_PPU_ALIAS` remains a legacy/deployment bootstrap fallback; it is not the only runtime selection mechanism for packaged Control Station operation.

## Resolution rules

For each Managed PPU request, the BFF resolves an alias in this order:

1. an explicit same-origin BFF selection recorded as an HttpOnly alias cookie;
2. a valid legacy `PLASMA_MANAGER_PPU_ALIAS` deployment value;
3. exactly one `commissioned` alias in the Manager registry.

If no unambiguous alias can be resolved, the Managed route fails closed. It never falls back to a direct Plasma Gateway URL or to registry ordering when multiple commissioned PPUs exist.

The selection endpoint accepts only a registry alias and verifies that the alias is already `commissioned` before recording it. Selection does not validate, enable, disable, remove, power, or otherwise mutate the physical PPU.

## Multi-PPU behavior

`Validate & Enable` and `select for Managed operations` are distinct lifecycle decisions. Commissioning a second PPU must not silently replace the current command target. When multiple commissioned PPUs exist, the operator explicitly selects which alias is used for Managed Programming and Diagnostics.

A single commissioned PPU is an unambiguous bootstrap case and may be selected automatically by the BFF without a host restart.

## Security boundary

The selection cookie contains only the registry alias. It is HttpOnly, same-origin, `SameSite=Strict`, and is never forwarded to Manager or the PPU. Manager remains the only component that resolves the alias to a Plasma Gateway Endpoint.

This contract does not change PPU authorization, Site scheduling, FPGA behavior, target power, or real-IC programming readiness.

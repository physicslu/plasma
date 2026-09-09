# STM32G0 Phase 4.8A — Foundation

## Scope

Phase 4.8A establishes a fail-closed, read-only STM32G0 source boundary for later official-ST discovery. It does not assert exact commercial ICPNs and does not authorize canonical or Production writes.

## OpenOCD source surface

The guarded STM32G0 source contains 182 rows and uses one target config:

- `tcl/target/stm32g0x.cfg`
- 143 `ordering_pattern` rows
- 39 `cmsis_device_name` rows
- all rows are `upstream-openocd`
- all rows are `mapping_candidate`
- all rows are `not_verified`

Unlike STM32F7, the STM32G0 source mixes commercial-ordering patterns with CMSIS aliases. Those surfaces are therefore separated explicitly.

### Commercial-routing surface

Only the 143 `ordering_pattern` rows may participate in deterministic Base Device selection. They remain routing evidence only; they are not manufacturer commercial-identity evidence.

### CMSIS-alias surface

The 39 `cmsis_device_name` rows are retained as routing/name metadata only. They do not participate in target selection and are never treated as exact commercial identity.

CMSIS aliases occur in these source subfamilies:

- STM32G071: 6
- STM32G081: 3
- STM32G0B1: 18
- STM32G0C1: 12

## Guarded subfamilies

| Subfamily | Total rows | Ordering patterns | CMSIS aliases |
|---|---:|---:|---:|
| STM32G030 | 6 | 6 | 0 |
| STM32G031 | 21 | 21 | 0 |
| STM32G041 | 14 | 14 | 0 |
| STM32G050 | 5 | 5 | 0 |
| STM32G051 | 13 | 13 | 0 |
| STM32G061 | 13 | 13 | 0 |
| STM32G070 | 3 | 3 | 0 |
| STM32G071 | 20 | 14 | 6 |
| STM32G081 | 11 | 8 | 3 |
| STM32G0B0 | 4 | 4 | 0 |
| STM32G0B1 | 43 | 25 | 18 |
| STM32G0C1 | 29 | 17 | 12 |

## Deterministic initial target set

One Base Device is selected per guarded subfamily by deterministic ordering-pattern order:

1. `STM32G030C6`
2. `STM32G031C4`
3. `STM32G041C6`
4. `STM32G050C6`
5. `STM32G051C6`
6. `STM32G061C6`
7. `STM32G070CB`
8. `STM32G071C8`
9. `STM32G081CB`
10. `STM32G0B0CE`
11. `STM32G0B1CB`
12. `STM32G0C1CC`

The set is a bounded research surface, not an assertion that these Base Devices are currently Active or that any exact ICPN exists today. Official ST evidence is required in the next phase.

## Trust boundary

Phase 4.8A explicitly does **not** claim:

- CMSIS alias = commercial identity
- manufacturer evidence retained
- exact commercial ICPN
- canonical dataset admission
- Production write authorization
- programming policy
- programming-algorithm equivalence
- physical/HIL qualification
- runtime programming support
- complete STM32G0 commercial-family coverage

## Next phase

Phase 4.8B will acquire official ST product evidence for the 12 deterministic targets and classify each target into manufacturer dispositions such as Active exact candidates, lifecycle exclusions, source-unavailable exclusions, or manual review. OpenOCD routing remains orthogonal to manufacturer identity.

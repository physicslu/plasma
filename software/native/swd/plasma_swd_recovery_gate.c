/* SPDX-License-Identifier: GPL-2.0-or-later
 * Inert Host-only SWD recovery admission seam; no hardware or Root authority.
 */
#include "plasma_swd_recovery_gate.h"

#include <stddef.h>
#include <string.h>
#include <unistd.h>

static int poison(struct plasma_swd_recovery_gate *gate, int code)
{
    if (gate) {
        gate->active = false;
        gate->poisoned = true;
    }
    return code;
}

int plasma_swd_recovery_gate_begin(
    struct plasma_swd_recovery_gate *gate,
    const struct plasma_swd_recovery_authority *authority,
    unsigned int site_id, uint64_t owner_epoch, const char *job_id)
{
    uint64_t generation = 0;
    if (!gate)
        return PLASMA_RECOVERY_DENIED;

    /* A reused object may never inherit its old in-process permission. */
    memset(gate, 0, sizeof(*gate));
    gate->poisoned = true;

    if (!authority || !authority->begin || !authority->check ||
        !authority->execute_while_owned ||
        (site_id != 1u && site_id != 2u) || owner_epoch == 0 ||
        !job_id || !*job_id || strlen(job_id) > 128u)
        return PLASMA_RECOVERY_DENIED;

    /* A future trusted PS-local authority MUST validate actual Site EX/
     * PPU SH ownership, current Boot/Image/Manifest, and persist UNCERTAIN
     * + intent. These injected callbacks are NOT authenticated here and
     * CAN be forged by callers. This helper alone is NOT a security gate.
     */
    if (authority->begin(authority->ctx, site_id, owner_epoch,
                         job_id, &generation) != 0 || generation == 0)
        return PLASMA_RECOVERY_DENIED;

    if (authority->check(authority->ctx, site_id, owner_epoch,
                         generation) != 0)
        return PLASMA_RECOVERY_DENIED;

    gate->authority = *authority;
    gate->site_id = site_id;
    gate->owner_epoch = owner_epoch;
    gate->generation = generation;
    gate->owner_pid = getpid();
    gate->active = true;
    gate->poisoned = false;
    return PLASMA_RECOVERY_OK;
}

int plasma_swd_recovery_gate_push(
    struct plasma_swd_recovery_gate *gate,
    unsigned int site_id, uint64_t owner_epoch,
    int (*push)(void *), void *push_ctx)
{
    if (!gate || !gate->active || gate->poisoned ||
        gate->site_id != site_id || gate->owner_epoch != owner_epoch ||
        gate->owner_pid != getpid() ||
        !gate->authority.execute_while_owned || !push)
        return poison(gate, PLASMA_RECOVERY_DENIED);

    /* The future trusted authority must hold the verified Site lease and
     * PPU Reload Fence across BOTH its check and the physical PUSH.
     * Separately checking then invoking push here creates a TOCTOU gap.
     * These are still injected Host-only callbacks, NOT trusted Root code.
     */
    const int result = gate->authority.execute_while_owned(
        gate->authority.ctx, site_id, owner_epoch, gate->generation,
        push, push_ctx);
    if (result == PLASMA_RECOVERY_OK)
        return PLASMA_RECOVERY_OK;
    if (result == PLASMA_RECOVERY_DENIED)
        return poison(gate, PLASMA_RECOVERY_DENIED);
    /* Unknown return or a possibly dispatched SWD operation: fail closed. */
    return poison(gate, PLASMA_RECOVERY_UNCERTAIN);
}

void plasma_swd_recovery_gate_retire(struct plasma_swd_recovery_gate *gate)
{
    if (gate) {
        memset(gate, 0, sizeof(*gate));
        gate->poisoned = true;
    }
}

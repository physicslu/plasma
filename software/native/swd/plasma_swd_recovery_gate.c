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
        (site_id != 1u && site_id != 2u) || owner_epoch == 0 ||
        !job_id || !*job_id || strlen(job_id) > 128u)
        return PLASMA_RECOVERY_DENIED;

    /* The external authority MUST validate actual Site EX/PPU SH ownership,
     * current Boot/Image/Manifest, and persist UNCERTAIN + intent. The
     * untrusted native caller cannot synthesize its own permission here.
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
        gate->owner_pid != getpid() || !gate->authority.check ||
        !push)
        return poison(gate, PLASMA_RECOVERY_DENIED);

    /* A live PS-local authority must verify this EXACT Owner generation on
     * EACH PUSH. The in-memory flag is deliberately insufficient.
     */
    if (gate->authority.check(gate->authority.ctx, site_id, owner_epoch,
                              gate->generation) != 0)
        return poison(gate, PLASMA_RECOVERY_DENIED);

    /* A callback can have accepted DUT-side effects even when it fails.
     * Poison the session; never retry or publish READY from this helper.
     */
    if (push(push_ctx) != 0)
        return poison(gate, PLASMA_RECOVERY_UNCERTAIN);
    return PLASMA_RECOVERY_OK;
}

void plasma_swd_recovery_gate_retire(struct plasma_swd_recovery_gate *gate)
{
    if (gate) {
        memset(gate, 0, sizeof(*gate));
        gate->poisoned = true;
    }
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only SWD crash-recovery C guard contract (Gate 1R).
 * No Root authority, MMIO, OpenOCD, or /dev/mem implementation is provided.
 * This inert adapter will be usable only when integrated into PR #1189's
 * exact Native C FIFO PUSH/normal-mode path by a separate reviewed change.
 */
#ifndef PLASMA_SWD_RECOVERY_GATE_H
#define PLASMA_SWD_RECOVERY_GATE_H

#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

enum plasma_swd_recovery_result {
    PLASMA_RECOVERY_OK = 0,
    PLASMA_RECOVERY_DENIED = -1,
    PLASMA_RECOVERY_UNCERTAIN = -2
};

/* begin() must durably establish UNCERTAIN BEFORE returning success.
 * check() only validates the initial session; a successful check is NOT
 * a grant to perform a later PUSH because authorization may be revoked.
 * execute_while_owned() MUST independently validate and hold the same
 * trusted PS Site lease/PPU reload fence across the entire PUSH callback.
 * No user-supplied function pointer authenticates the Root authority.
 * Neither callback is implemented here. Neither may clear uncertainty.
 */
struct plasma_swd_recovery_authority {
    void *ctx;
    int (*begin)(void *ctx, unsigned int site_id,
                 uint64_t owner_epoch, const char *job_id,
                 uint64_t *generation);
    int (*check)(void *ctx, unsigned int site_id,
                 uint64_t owner_epoch, uint64_t generation);
    /* 0=success, DENIED=not dispatched, UNCERTAIN=may have dispatched.
     * Must hold trusted Owner and Reload Fence while invoking push().
     */
    int (*execute_while_owned)(void *ctx, unsigned int site_id,
                               uint64_t owner_epoch, uint64_t generation,
                               int (*push)(void *), void *push_ctx);
};

/* In-memory session is NEVER sufficient across process death or FPGA reload.
 * Caller must own a valid lock/Root-qualified hardware Site independently.
 */
struct plasma_swd_recovery_gate {
    struct plasma_swd_recovery_authority authority;
    unsigned int site_id;
    uint64_t owner_epoch;
    uint64_t generation;
    pid_t owner_pid;
    bool active;
    bool poisoned;
};

/* Begin a single live-Owner multi-PUSH session; initially denied by default.
 * All inputs and callbacks must be sourced by a trusted integration.
 */
int plasma_swd_recovery_gate_begin(
    struct plasma_swd_recovery_gate *gate,
    const struct plasma_swd_recovery_authority *authority,
    unsigned int site_id, uint64_t owner_epoch, const char *job_id);

/* Candidate seam for EACH Native C FIFO PUSH, not yet wired to #1189.
 * The trusted authority executes the callback INSIDE its lease/fence critical
 * section; an earlier standalone check is insufficient (TOCTOU). A successful
 * PUSH leaves durable UNCERTAIN in place, with no automatic retry/clear.
 */
int plasma_swd_recovery_gate_push(
    struct plasma_swd_recovery_gate *gate,
    unsigned int site_id, uint64_t owner_epoch,
    int (*push)(void *), void *push_ctx);

/* Retire only the in-process lease. Never issue READY or remove intent. */
void plasma_swd_recovery_gate_retire(struct plasma_swd_recovery_gate *gate);

#endif

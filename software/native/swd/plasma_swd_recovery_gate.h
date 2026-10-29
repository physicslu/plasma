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
 * check() must independently revalidate the trusted PS-local session and
 * Site lease epoch; a numeric generation is NOT a security credential.
 * Neither callback is implemented here. Neither may clear uncertainty.
 */
struct plasma_swd_recovery_authority {
    void *ctx;
    int (*begin)(void *ctx, unsigned int site_id,
                 uint64_t owner_epoch, const char *job_id,
                 uint64_t *generation);
    int (*check)(void *ctx, unsigned int site_id,
                 uint64_t owner_epoch, uint64_t generation);
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

/* This is the mandatory seam intended to wrap EACH Native C FIFO PUSH.
 * Validation precedes any callback and fails closed on any error.
 * A successful PUSH leaves durable UNCERTAIN in place; no auto-clear.
 */
int plasma_swd_recovery_gate_push(
    struct plasma_swd_recovery_gate *gate,
    unsigned int site_id, uint64_t owner_epoch,
    int (*push)(void *), void *push_ctx);

/* Retire only the in-process lease. Never issue READY or remove intent. */
void plasma_swd_recovery_gate_retire(struct plasma_swd_recovery_gate *gate);

#endif

/* SPDX-License-Identifier: GPL-2.0-or-later
 * PS Linux Native C mapped-word owner boundary for candidate SWD ABI v5.
 * The caller supplies an already-opened, owned descriptor and a
 * same-process authoritative C Root/Image/voltage/Site callback.
 * This module does NOT open /dev/mem, acquire privileges, or make a
 * mock callback into real Root attestation.
 */
#ifndef PLASMA_SWD_PS_MAPPING_H
#define PLASMA_SWD_PS_MAPPING_H
#include "plasma_swd_native_words.h"
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

struct plasma_swd_ps_mapping {
    void *mapped;
    size_t mapped_bytes;
    pid_t pid;
    bool active;
    struct plasma_swd_native_words native;
};

/* Mapping is intentionally distinct from FIFO admission. It requires a
 * per-Site lock held before mmap, a nonzero Site lease generation, and
 * an external authorization callback checked BEFORE mmap and thereafter
 * on every native C transaction. The FD is borrowed, not closed.
 *
 * Production accepts only an O_RDWR|O_SYNC /dev/mem char device FD with
 * FD_CLOEXEC. Host-only builds (PLASMA_SWD_HOST_TEST) accept regular
 * sparse files to simulate the physical address aperture.
 * Do not call this from an unqualified launch/Root process.
 */
int plasma_swd_ps_mapping_attach(
    struct plasma_swd_ps_mapping *mapping, int preopened_fd,
    const struct plasma_swd_owner_lock *owner,
    unsigned int site_id, uint64_t lease_generation,
    void *authority_ctx,
    int (*authorize)(void *, unsigned int, uint64_t),
    void (*revoke_all)(void *));

/* The live OpenOCD/FIFO binding must be terminated BEFORE detach.
 * Retires its Native C words first, unmaps exactly one 4KiB Site page;
 * no hardware registers are written on cleanup. */
void plasma_swd_ps_mapping_detach(struct plasma_swd_ps_mapping *mapping);
#endif

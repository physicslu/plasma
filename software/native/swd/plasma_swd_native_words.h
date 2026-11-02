/* SPDX-License-Identifier: GPL-2.0-or-later
 * PLASMA ABI-v5 PS-native 32-bit MMIO word access.
 * Reuses an EXISTING trusted owner mapping (PR #1199 pattern).
 * No /dev/mem open, mmap, socket, Python callback, SWD bitbang or auth grant.
 */
#ifndef PLASMA_SWD_NATIVE_WORDS_H
#define PLASMA_SWD_NATIVE_WORDS_H

#include "plasma_swd_lease_word_port.h"
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <sys/types.h>

#define PLASMA_SWD_NATIVE_PAGE_BYTES 4096u

struct plasma_swd_native_words {
    volatile uint32_t *words;
    const struct plasma_swd_owner_lock *owner;
    uint64_t owner_epoch;
    unsigned int site;
    uint32_t base;
    uint64_t lease_generation;
    pid_t pid;
    void *authority_ctx;
    /* A trusted SAME-PROCESS native-C owner must validate current
     * Root source, Boot ID, Image+Manifest, voltage, and Site lease.
     * Must reject if any signal is missing, stale or unsafe.
     */
    int (*authorize)(void *authority_ctx, unsigned int site,
                     uint64_t lease_generation);
    /* Must revoke BOTH Sites in the shared owner domain on uncertainty. */
    void (*revoke_all)(void *authority_ctx);
    bool poisoned;
};

int plasma_swd_native_words_init(
    struct plasma_swd_native_words *native,
    volatile uint32_t *already_owned_words, size_t mapped_size,
    const struct plasma_swd_owner_lock *owner,
    unsigned int site, uint64_t lease_generation,
    void *authority_ctx,
    int (*authorize)(void *, unsigned int, uint64_t),
    void (*revoke_all)(void *));

/* Produces the C provider consumed by existing Lease Word Port.
 * Call the Lease Port's admit() BEFORE any SWD FIFO activity.
 */
/* Pure owner/Root/Boot/Image/voltage callback re-check; no MMIO I/O. */
int plasma_swd_native_words_ready(struct plasma_swd_native_words *native);
struct plasma_swd_lease_provider plasma_swd_native_words_provider(
    struct plasma_swd_native_words *native);
bool plasma_swd_native_words_armv7_dmb(void);
void plasma_swd_native_words_retire(struct plasma_swd_native_words *native);
#endif

/* SPDX-License-Identifier: GPL-2.0-or-later
 * ABI-v5 native C 32-bit volatile MMIO engine, inspired by merged PR #1199
 * its 32-bit MMIO instruction technique. Hardware admission remains external and is
 * rechecked at each C operation. NO independent device owner is installed.
 *
 * On ARMv7 the compiler must emit word LDR/STR and DMB SY, separately
 * confirmed by exact-target disassembly. Device memory attributes, AXI
 * completion, SIGBUS and physical FPGA behavior are NOT established by C.
 */
#include "plasma_swd_native_words.h"
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

_Static_assert(sizeof(uint32_t) == 4, "Native word access must be 32-bit");

static inline void dmb_sy(void)
{
#if defined(__arm__) && defined(__ARM_ARCH_7A__)
    __asm__ __volatile__("dmb sy" ::: "memory");
#else
    atomic_signal_fence(memory_order_seq_cst); /* Host-only, NOT ARM barrier */
#endif
}

bool plasma_swd_native_words_armv7_dmb(void)
{
#if defined(__arm__) && defined(__ARM_ARCH_7A__)
    return true;
#else
    return false;
#endif
}

static bool valid_offset(uint32_t off, bool write)
{
    if ((off & 3u) != 0 || off >= PLASMA_SWD_NATIVE_PAGE_BYTES)
        return false;
    if (write) {
        switch (off) {
        case 0x08: case 0x0c: case 0x10: case 0x14: case 0x20:
        case 0x28: case 0x2c: case 0x30: case 0x34: case 0x38:
        case 0x44: case 0x48: case 0x4c: case 0x50: case 0x54:
        case 0x58: case 0x5c: case 0x60: case 0x64:
            return true;
        default: return false;
        }
    }
    switch (off) {
    case 0x00: case 0x04: case 0x08: case 0x0c: case 0x18:
    case 0x1c: case 0x24: case 0x28: case 0x2c: case 0x30:
    case 0x34: case 0x38:
        return true;
    default: return false;
    }
}

static int qualified(struct plasma_swd_native_words *n,
                     unsigned int site, uint32_t base, uint64_t generation)
{
    if (!n || n->poisoned || !n->words ||
        n->site != site || n->base != base ||
        n->lease_generation != generation || n->pid != getpid() ||
        !plasma_swd_owner_lock_valid(n->owner) ||
        n->owner_epoch != n->owner->epoch ||
        (n->owner->site_id != 0 && n->owner->site_id != site) ||
        !n->authorize || !n->revoke_all ||
        n->authorize(n->authority_ctx, site, generation) != 0)
        return -1;
    return 0;
}

int plasma_swd_native_words_ready(struct plasma_swd_native_words *n)
{
    if (!n)
        return PLASMA_SWD_NOT_READY;
    return qualified(n, n->site, n->base, n->lease_generation)
        == 0 ? PLASMA_SWD_OK : PLASMA_SWD_NOT_READY;
}

static int native_qualify(void *ctx, unsigned int site, uint32_t base,
                          uint64_t generation)
{
    struct plasma_swd_native_words *n = ctx;
    if (qualified(n, site, base, generation))
        return -1;
    /* Identity is observed with a volatile 32-bit access, before admission.
     * This does NOT prove the Image is Root/Manifest approved; that is the
     * independent native authority's responsibility.
     */
    dmb_sy();
    uint32_t image_id = n->words[0];
    dmb_sy();
    if (image_id != (PLASMA_SWD_ABI_V5 | site))
        return -1;
    return 0;
}

static int native_read(void *ctx, unsigned int site, uint32_t base,
                       uint64_t generation, uint32_t address,
                       uint32_t *value)
{
    struct plasma_swd_native_words *n = ctx;
    if (!value || qualified(n, site, base, generation) ||
        address < base || !valid_offset(address - base, false))
        return -1;
    dmb_sy();
    uint32_t read_value = n->words[(address - base) / sizeof(uint32_t)];
    dmb_sy();
    *value = read_value;
    return 0;
}

static int native_write(void *ctx, unsigned int site, uint32_t base,
                        uint64_t generation, uint32_t address, uint32_t value)
{
    struct plasma_swd_native_words *n = ctx;
    if (qualified(n, site, base, generation) || address < base ||
        !valid_offset(address - base, true))
        return -1;
    n->words[(address - base) / sizeof(uint32_t)] = value;
    /* No error return from a volatile store proves AXI completion. The
     * following barrier is also invoked by the FIFO Core separately. */
    dmb_sy();
    return 0;
}

static int native_barrier(void *ctx, unsigned int site, uint32_t base,
                          uint64_t generation)
{
    struct plasma_swd_native_words *n = ctx;
    if (qualified(n, site, base, generation))
        return -1;
    dmb_sy();
    return 0;
}

static void native_revoke_all(void *ctx)
{
    struct plasma_swd_native_words *n = ctx;
    if (!n || n->poisoned)
        return;
    n->poisoned = true;
    n->revoke_all(n->authority_ctx);
}

int plasma_swd_native_words_init(
    struct plasma_swd_native_words *n,
    volatile uint32_t *already_owned_words, size_t mapped_size,
    const struct plasma_swd_owner_lock *owner,
    unsigned int site, uint64_t generation,
    void *authority_ctx,
    int (*authorize)(void *, unsigned int, uint64_t),
    void (*revoke_all)(void *))
{
    if (!n || !already_owned_words ||
        ((uintptr_t)already_owned_words & (sizeof(uint32_t) - 1u)) != 0 ||
        mapped_size != PLASMA_SWD_NATIVE_PAGE_BYTES ||
        !plasma_swd_owner_lock_valid(owner) ||
        (owner->site_id != 0 && owner->site_id != site) ||
        (site != 1 && site != 2) || generation == 0 ||
        !authorize || !revoke_all)
        return PLASMA_SWD_BAD_ARG;
    memset(n, 0, sizeof(*n));
    n->words = already_owned_words;
    n->owner = owner;
    n->owner_epoch = owner->epoch;
    n->site = site;
    n->base = site == 1 ? PLASMA_SWD_SITE1_BASE : PLASMA_SWD_SITE2_BASE;
    n->lease_generation = generation;
    n->pid = getpid();
    n->authority_ctx = authority_ctx;
    n->authorize = authorize;
    n->revoke_all = revoke_all;
    return PLASMA_SWD_OK;
}

struct plasma_swd_lease_provider plasma_swd_native_words_provider(
    struct plasma_swd_native_words *n)
{
    return (struct plasma_swd_lease_provider){
        .ctx = n, .qualify = native_qualify,
        .read_owned = native_read, .write_owned = native_write,
        .barrier_owned = native_barrier,
        .invalidate_all = native_revoke_all,
    };
}

void plasma_swd_native_words_retire(struct plasma_swd_native_words *n)
{
    if (!n)
        return;
    n->poisoned = true;
    n->words = NULL;
}

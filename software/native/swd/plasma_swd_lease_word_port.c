/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only-capable ABI-v5 owner/lease contract, NO device-backed port.
 * Production provider callbacks are deliberately NOT supplied here.
 */
#include "plasma_swd_lease_word_port.h"
#include <stddef.h>
#include <string.h>
#include <unistd.h>

static bool can_access(const struct plasma_swd_lease_word_port *p)
{
    return p && p->admitted && !p->poisoned &&
           p->creator_pid == getpid() &&
           plasma_swd_owner_lock_valid(p->process_lock) &&
           p->owner_lock_epoch == p->process_lock->epoch;
}
static void poison(struct plasma_swd_lease_word_port *p)
{
    if (!p || p->poisoned)
        return;
    p->poisoned = true;
    p->admitted = false;
    /* The provider MUST invalidate all Site generations in its owner
     * domain; this handles uncertain writes across shared AXI mappings. */
    p->provider.invalidate_all(p->provider.ctx);
}
static bool offset_ok(const struct plasma_swd_lease_word_port *p,
                      uint32_t addr, bool write)
{
    if (addr < p->base || (addr & 3u) || addr - p->base >= 4096u)
        return false;
    uint32_t off = addr - p->base;
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

int plasma_swd_lease_word_port_init(struct plasma_swd_lease_word_port *p,
                                   const struct plasma_swd_lease_provider *owner,
                                   const struct plasma_swd_owner_lock *process_lock,
                                   unsigned int site, uint64_t generation)
{
    if (!p || !owner || !plasma_swd_owner_lock_valid(process_lock) ||
        (process_lock->site_id != 0u && process_lock->site_id != site) ||
        (site != 1 && site != 2) || generation == 0 ||
        !owner->qualify || !owner->read_owned || !owner->write_owned ||
        !owner->barrier_owned || !owner->invalidate_all)
        return PLASMA_SWD_BAD_ARG;
    memset(p, 0, sizeof(*p));
    p->provider = *owner;
    p->site_id = site;
    p->base = site == 1 ? PLASMA_SWD_SITE1_BASE : PLASMA_SWD_SITE2_BASE;
    p->generation = generation;
    p->process_lock = process_lock;
    p->owner_lock_epoch = process_lock->epoch;
    p->creator_pid = getpid();
    return PLASMA_SWD_OK;
}
int plasma_swd_lease_word_port_admit(struct plasma_swd_lease_word_port *p)
{
    if (!p || p->poisoned || p->admitted || p->creator_pid != getpid() ||
        !plasma_swd_owner_lock_valid(p->process_lock) ||
        p->owner_lock_epoch != p->process_lock->epoch)
        return PLASMA_SWD_NOT_READY;
    if (p->provider.qualify(p->provider.ctx, p->site_id, p->base,
                            p->generation) != 0) {
        p->poisoned = true; /* no hardware side effects */
        return PLASMA_SWD_NOT_READY;
    }
    p->admitted = true;
    return PLASMA_SWD_OK;
}
static int read32(void *ctx, uint32_t addr, uint32_t *value)
{
    struct plasma_swd_lease_word_port *p = ctx;
    if (!can_access(p) || !value || !offset_ok(p, addr, false))
        return -1; /* prevalidation is not a hardware/bus failure */
    if (p->provider.read_owned(p->provider.ctx, p->site_id, p->base,
                               p->generation, addr, value) != 0) {
        poison(p);
        return -1;
    }
    return 0;
}
static int write32(void *ctx, uint32_t addr, uint32_t value)
{
    struct plasma_swd_lease_word_port *p = ctx;
    if (!can_access(p) || !offset_ok(p, addr, true))
        return -1;
    if (p->provider.write_owned(p->provider.ctx, p->site_id, p->base,
                                p->generation, addr, value) != 0) {
        poison(p);
        return -1;
    }
    return 0;
}
static int write_barrier(void *ctx)
{
    struct plasma_swd_lease_word_port *p = ctx;
    if (!can_access(p))
        return -1;
    if (p->provider.barrier_owned(p->provider.ctx, p->site_id, p->base,
                                  p->generation) != 0) {
        poison(p);
        return -1;
    }
    return 0;
}
int plasma_swd_lease_word_port_make_io(struct plasma_swd_lease_word_port *p,
                                       struct plasma_swd_word_io *io)
{
    if (!io || !can_access(p))
        return PLASMA_SWD_NOT_READY;
    *io = (struct plasma_swd_word_io){
        .ctx = p, .read32 = read32, .write32 = write32,
        .write_barrier = write_barrier,
    };
    return PLASMA_SWD_OK;
}
void plasma_swd_lease_word_port_retire(struct plasma_swd_lease_word_port *p)
{
    if (!p)
        return;
    p->admitted = false;
    p->poisoned = true;
}

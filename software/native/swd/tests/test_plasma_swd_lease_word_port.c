#define _POSIX_C_SOURCE 200809L
/* SPDX-License-Identifier: GPL-2.0-or-later
 * Pure Host-only synthetic owner test: no device node, no mmap, no GPIO.
 * Provider must enforce authorization INSIDE each owned access callback.
 */
#include "../plasma_swd_lease_word_port.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

static struct plasma_swd_owner_lock process_lock = {.fd = -1};

struct domain {
    uint64_t generations[2];
    int verified_image, voltage_safe, root_owner, valid;
    int fail_barrier, fail_write;
    unsigned int qualifications, writes, reads, invalidations, pushes;
    uint32_t mode[2], enabled[2], meta[2], rx[2], levels[2];
};

static int owned(struct domain *d, unsigned int site, uint32_t base,
                 uint64_t gen)
{
    if (site < 1 || site > 2 || !d->valid || !d->verified_image ||
        !d->voltage_safe || !d->root_owner)
        return -1;
    if (base != (site == 1 ? PLASMA_SWD_SITE1_BASE : PLASMA_SWD_SITE2_BASE))
        return -1;
    return gen == d->generations[site - 1] ? 0 : -1;
}
static int qualify(void *ctx, unsigned int site, uint32_t base, uint64_t gen)
{
    struct domain *d = ctx;
    d->qualifications++;
    return owned(d, site, base, gen);
}
static int read_owned(void *ctx, unsigned int site, uint32_t base,
                      uint64_t gen, uint32_t addr, uint32_t *v)
{
    struct domain *d = ctx;
    if (owned(d, site, base, gen) || !v)
        return -1;
    d->reads++;
    unsigned int i = site - 1;
    switch (addr - base) {
    case 0x00: *v = PLASMA_SWD_ABI_V5 | site; break;
    case 0x04: *v = d->enabled[i]; break;
    case 0x18: *v = d->meta[i]; break;
    case 0x1c: *v = d->rx[i]; break;
    case 0x24: *v = d->levels[i]; break;
    case 0x38: *v = d->mode[i]; break;
    default: *v = 0; break;
    }
    return 0;
}
static int write_owned(void *ctx, unsigned int site, uint32_t base,
                       uint64_t gen, uint32_t addr, uint32_t value)
{
    struct domain *d = ctx;
    if (owned(d, site, base, gen) || d->fail_write)
        return -1;
    d->writes++;
    unsigned int i = site - 1;
    switch (addr - base) {
    case 0x38: d->mode[i] = value; break;
    case 0x28: d->enabled[i] = value & 1u; break;
    case 0x14:
        d->pushes++;
        d->meta[i] = (value & 0xffff0000u) | 0x90u;
        d->rx[i] = 0x1ba01477u;
        d->levels[i] = 2u;
        break;
    case 0x20: d->levels[i] = 0u; break;
    default: break;
    }
    return 0;
}
static int barrier_owned(void *ctx, unsigned int site, uint32_t base,
                         uint64_t gen)
{
    struct domain *d = ctx;
    return owned(d, site, base, gen) || d->fail_barrier ? -1 : 0;
}
static void invalidate_all(void *ctx)
{
    struct domain *d = ctx;
    d->valid = 0;
    d->invalidations++;
}
static struct plasma_swd_lease_provider provider(struct domain *d)
{
    return (struct plasma_swd_lease_provider){
        .ctx = d, .qualify = qualify, .read_owned = read_owned,
        .write_owned = write_owned, .barrier_owned = barrier_owned,
        .invalidate_all = invalidate_all,
    };
}
static void setup(struct domain *d)
{
    memset(d, 0, sizeof(*d));
    d->verified_image = d->voltage_safe = d->root_owner = d->valid = 1;
    d->generations[0] = 11;
    d->generations[1] = 22;
}
static void test_guarded_c_fifo_two_sites(void)
{
    struct domain d;
    setup(&d);
    struct plasma_swd_lease_word_port a, b;
    struct plasma_swd_lease_provider owner = provider(&d);
    assert(plasma_swd_lease_word_port_init(&a, &owner, &process_lock, 1, 11) == 0);
    assert(plasma_swd_lease_word_port_init(&b, &owner, &process_lock, 2, 22) == 0);
    assert(d.qualifications == 0 && d.reads == 0 && d.writes == 0);
    struct plasma_swd_word_io io_a, io_b;
    assert(plasma_swd_lease_word_port_make_io(&a, &io_a) == PLASMA_SWD_NOT_READY);
    assert(plasma_swd_lease_word_port_admit(&a) == 0);
    assert(plasma_swd_lease_word_port_admit(&b) == 0);
    assert(plasma_swd_lease_word_port_make_io(&a, &io_a) == 0);
    assert(plasma_swd_lease_word_port_make_io(&b, &io_b) == 0);
    uint32_t v = 0;
    assert(io_a.read32(io_a.ctx, PLASMA_SWD_SITE2_BASE, &v) != 0);
    assert(io_b.write32(io_b.ctx, PLASMA_SWD_SITE1_BASE + 0x38, 1) != 0);
    assert(io_a.read32(io_a.ctx, PLASMA_SWD_SITE1_BASE + 0x3c, &v) != 0);
    assert(io_a.write32(io_a.ctx, PLASMA_SWD_SITE1_BASE + 0x40, 1) != 0);
    assert(io_a.write32(io_a.ctx, PLASMA_SWD_SITE1_BASE + 0x00, 1) != 0);
    assert(io_a.read32(io_a.ctx, PLASMA_SWD_SITE1_BASE + 0x10, &v) != 0);
    assert(io_a.read32(io_a.ctx, PLASMA_SWD_SITE1_BASE + 1, &v) != 0);
    assert(d.reads == 0 && d.writes == 0);
    struct plasma_swd_fifo site1, site2;
    assert(plasma_swd_fifo_init(&site1, &io_a, 1, 8) == 0);
    assert(plasma_swd_fifo_init(&site2, &io_b, 2, 8) == 0);
    assert(plasma_swd_fifo_admit(&site1) == 0);
    assert(plasma_swd_fifo_admit(&site2) == 0);
    uint32_t got1 = 0, got2 = 0;
    assert(plasma_swd_fifo_queue_read(&site1, 0x24, &got1, 0) == 0);
    assert(plasma_swd_fifo_queue_read(&site2, 0x24, &got2, 0) == 0);
    assert(plasma_swd_fifo_run(&site1) == 0);
    assert(plasma_swd_fifo_run(&site2) == 0);
    assert(got1 == 0x1ba01477u && got2 == got1 && d.pushes == 2);
    assert(d.invalidations == 0);
    /* Revocation MUST be checked inside every read/write/barrier,
     * not just the initial Site admission or by a stale success flag. */
    d.generations[0]++;
    assert(io_a.read32(io_a.ctx, PLASMA_SWD_SITE1_BASE, &v) != 0);
    assert(d.invalidations == 1 && !d.valid && a.poisoned);
    assert(io_b.read32(io_b.ctx, PLASMA_SWD_SITE2_BASE, &v) != 0);
    assert(d.invalidations == 2 && b.poisoned);
}
static void test_bad_owner_and_barrier_fail_closed(void)
{
    struct domain d;
    setup(&d);
    struct plasma_swd_lease_word_port a, b;
    struct plasma_swd_lease_provider owner = provider(&d);
    assert(plasma_swd_lease_word_port_init(&a, &owner, &process_lock, 1, 0) == PLASMA_SWD_BAD_ARG);
    assert(plasma_swd_lease_word_port_init(&a, &owner, &process_lock, 3, 11) == PLASMA_SWD_BAD_ARG);
    d.voltage_safe = 0;
    assert(plasma_swd_lease_word_port_init(&a, &owner, &process_lock, 1, 11) == 0);
    assert(plasma_swd_lease_word_port_admit(&a) == PLASMA_SWD_NOT_READY);
    assert(a.poisoned && d.writes == 0 && d.invalidations == 0);
    d.voltage_safe = 1;
    assert(plasma_swd_lease_word_port_admit(&a) == PLASMA_SWD_NOT_READY);
    assert(plasma_swd_lease_word_port_init(&a, &owner, &process_lock, 1, 11) == 0);
    assert(plasma_swd_lease_word_port_init(&b, &owner, &process_lock, 2, 22) == 0);
    assert(plasma_swd_lease_word_port_admit(&a) == 0);
    assert(plasma_swd_lease_word_port_admit(&b) == 0);
    struct plasma_swd_word_io io_a, io_b;
    assert(plasma_swd_lease_word_port_make_io(&a, &io_a) == 0);
    assert(plasma_swd_lease_word_port_make_io(&b, &io_b) == 0);
    d.fail_barrier = 1;
    assert(io_a.write32(io_a.ctx, PLASMA_SWD_SITE1_BASE + 0x38, 1) == 0);
    assert(io_a.write_barrier(io_a.ctx) != 0);
    assert(a.poisoned && d.invalidations == 1);
    assert(io_b.read32(io_b.ctx, PLASMA_SWD_SITE2_BASE, &d.mode[1]) != 0);
    assert(b.poisoned && d.invalidations == 2);
    plasma_swd_lease_word_port_retire(&a);
    assert(io_a.read32(io_a.ctx, PLASMA_SWD_SITE1_BASE, &d.mode[0]) != 0);
}
int main(void)
{
    char path[] = "/tmp/plasma-swd-owner-host-XXXXXX";
    int fd = mkstemp(path);
    assert(fd >= 0);
    close(fd);
    assert(plasma_swd_owner_lock_acquire(&process_lock, path) == 0);
    test_guarded_c_fifo_two_sites();
    test_bad_owner_and_barrier_fail_closed();
    /* Releasing and reacquiring the same cooperative lock is a NEW epoch.
     * A stale C Site token must never silently become active again. */
    struct domain d;
    setup(&d);
    struct plasma_swd_lease_word_port stale;
    struct plasma_swd_lease_provider owner = provider(&d);
    assert(plasma_swd_lease_word_port_init(
        &stale, &owner, &process_lock, 1, 11) == 0);
    assert(plasma_swd_lease_word_port_admit(&stale) == 0);
    struct plasma_swd_word_io io;
    assert(plasma_swd_lease_word_port_make_io(&stale, &io) == 0);
    const uint64_t epoch = process_lock.epoch;
    plasma_swd_owner_lock_release(&process_lock);
    uint32_t value = 0;
    assert(io.read32(io.ctx, PLASMA_SWD_SITE1_BASE, &value) != 0);
    assert(plasma_swd_owner_lock_acquire(&process_lock, path) == 0);
    assert(process_lock.epoch != epoch);
    assert(io.read32(io.ctx, PLASMA_SWD_SITE1_BASE, &value) != 0);
    assert(d.reads == 0);
    plasma_swd_owner_lock_release(&process_lock);
    assert(unlink(path) == 0);
    puts("PLASMA_NATIVE_SWD_LEASE_PORT_HOST_ONLY_PASS");
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only sparse-file test of PS-local C mmap lifecycle and v5 admission.
 * Must be compiled with PLASMA_SWD_HOST_TEST. No /dev/mem or DUT access.
 */
#define _GNU_SOURCE
#include "../plasma_swd_ps_mapping.h"
#include <assert.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

struct test_authority {
    bool root, boot, image, manifest, voltage, current;
    uint64_t gen[2];
    unsigned checks, revoked;
};
static int authorize(void *ctx, unsigned site, uint64_t gen)
{
    struct test_authority *a = ctx;
    a->checks++;
    return site > 0 && site <= 2 && gen == a->gen[site - 1] &&
        a->root && a->boot && a->image && a->manifest &&
        a->voltage && a->current ? 0 : -1;
}
static void revoke_all(void *ctx)
{
    struct test_authority *a = ctx;
    a->current = false;
    a->revoked++;
}
static void put32(int fd, uint32_t address, uint32_t value)
{
    assert(pwrite(fd, &value, 4, (off_t)address) == 4);
}
static uint32_t get32(int fd, uint32_t address)
{
    uint32_t value = 0;
    assert(pread(fd, &value, 4, (off_t)address) == 4);
    return value;
}
int main(void)
{
#ifndef PLASMA_SWD_HOST_TEST
#error "This test must never access a real device"
#endif
    char data[] = "/tmp/plasma-ps-mapping-data-XXXXXX";
    char lock_path[] = "/tmp/plasma-ps-mapping-lock-XXXXXX";
    int raw = mkstemp(data), lockfd = mkstemp(lock_path);
    assert(raw >= 0 && lockfd >= 0);
    assert(close(raw) == 0 && close(lockfd) == 0);
    int fd = open(data, O_RDWR | O_SYNC | O_CLOEXEC);
    assert(fd >= 0);
    const uint32_t last = PLASMA_SWD_SITE2_BASE + 4096u;
    assert(ftruncate(fd, (off_t)last) == 0);
    put32(fd, PLASMA_SWD_SITE1_BASE, PLASMA_SWD_ABI_V5 | 1);
    put32(fd, PLASMA_SWD_SITE2_BASE, PLASMA_SWD_ABI_V5 | 2);
    put32(fd, PLASMA_SWD_SITE1_BASE + 4, 1);
    put32(fd, PLASMA_SWD_SITE2_BASE + 4, 1);
    struct plasma_swd_owner_lock l1 = {.fd = -1, .site_fd = -1};
    struct plasma_swd_owner_lock l2 = {.fd = -1, .site_fd = -1};
    assert(plasma_swd_owner_lock_acquire_site(&l1, lock_path, 1) == 0);
    assert(plasma_swd_owner_lock_acquire_site(&l2, lock_path, 2) == 0);
    struct test_authority a = {
        .root = true, .boot = true, .image = true,
        .manifest = true, .voltage = true, .current = true,
        .gen = {11, 22},
    };
    struct plasma_swd_ps_mapping one = {0}, two = {0};
    /* The supplied fd, not a pathname, controls the mapped source.
     * A wrong file type/read-only FD, missing authority or wrong Site
     * cannot establish any map.
     */
    int readonly = open(data, O_RDONLY | O_CLOEXEC);
    assert(readonly >= 0);
    assert(plasma_swd_ps_mapping_attach(&one, readonly, &l1, 1, 11,
           &a, authorize, revoke_all) == PLASMA_SWD_NOT_READY);
    assert(!one.active && !one.mapped);
    assert(close(readonly) == 0);
    assert(plasma_swd_ps_mapping_attach(&one, fd, &l2, 1, 11,
           &a, authorize, revoke_all) == PLASMA_SWD_BAD_ARG);
    assert(plasma_swd_ps_mapping_attach(&one, fd, &l1, 1, 0,
           &a, authorize, revoke_all) == PLASMA_SWD_BAD_ARG);
    a.voltage = false;
    assert(plasma_swd_ps_mapping_attach(&one, fd, &l1, 1, 11,
           &a, authorize, revoke_all) == PLASMA_SWD_NOT_READY);
    assert(!one.active && !one.mapped);
    a.voltage = true;

    assert(plasma_swd_ps_mapping_attach(&one, fd, &l1, 1, 11,
           &a, authorize, revoke_all) == PLASMA_SWD_OK);
    assert(plasma_swd_ps_mapping_attach(&two, fd, &l2, 2, 22,
           &a, authorize, revoke_all) == PLASMA_SWD_OK);
    assert(plasma_swd_ps_mapping_attach(&one, fd, &l1, 1, 11,
           &a, authorize, revoke_all) == PLASMA_SWD_BAD_ARG);
    assert(one.native.words != two.native.words);
    assert(one.native.base == PLASMA_SWD_SITE1_BASE);
    assert(two.native.base == PLASMA_SWD_SITE2_BASE);
    struct plasma_swd_lease_provider p1 = plasma_swd_native_words_provider(&one.native);
    struct plasma_swd_lease_provider p2 = plasma_swd_native_words_provider(&two.native);
    struct plasma_swd_lease_word_port port1, port2;
    assert(plasma_swd_lease_word_port_init(&port1, &p1, &l1, 1, 11) == 0);
    assert(plasma_swd_lease_word_port_init(&port2, &p2, &l2, 2, 22) == 0);
    assert(plasma_swd_lease_word_port_admit(&port1) == 0);
    assert(plasma_swd_lease_word_port_admit(&port2) == 0);
    struct plasma_swd_word_io io1, io2;
    assert(plasma_swd_lease_word_port_make_io(&port1, &io1) == 0);
    assert(plasma_swd_lease_word_port_make_io(&port2, &io2) == 0);
    struct plasma_swd_fifo fifo1, fifo2;
    assert(plasma_swd_fifo_init(&fifo1, &io1, 1, 5) == 0);
    assert(plasma_swd_fifo_init(&fifo2, &io2, 2, 5) == 0);
    assert(plasma_swd_fifo_admit(&fifo1) == 0);
    assert(plasma_swd_fifo_admit(&fifo2) == 0);
    assert(get32(fd, PLASMA_SWD_SITE1_BASE + 0x38u) == 1u);
    assert(get32(fd, PLASMA_SWD_SITE2_BASE + 0x38u) == 1u);
    assert(io1.write32(io1.ctx, PLASMA_SWD_SITE1_BASE + 0x10u,
                       0xA5A55A5Au) == 0);
    assert(get32(fd, PLASMA_SWD_SITE1_BASE + 0x10u) == 0xA5A55A5Au);
    assert(get32(fd, PLASMA_SWD_SITE2_BASE + 0x10u) == 0u);

    /* Revoking the trusted owner cannot leave accessible old mappings.
     * Both Site ports must stop even though mmap still exists.
     */
    a.current = false;
    assert(plasma_swd_native_words_ready(&one.native) != 0);
    assert(io1.write32(io1.ctx, PLASMA_SWD_SITE1_BASE + 0x10u, 9) != 0);
    assert(a.revoked == 1 && !port1.admitted && port1.poisoned);
    assert(get32(fd, PLASMA_SWD_SITE1_BASE + 0x10u) == 0xA5A55A5Au);
    assert(io2.write32(io2.ctx, PLASMA_SWD_SITE2_BASE + 0x10u, 9) != 0);
    assert(a.revoked == 2 && !port2.admitted && port2.poisoned);

    plasma_swd_lease_word_port_retire(&port1);
    plasma_swd_lease_word_port_retire(&port2);
    plasma_swd_ps_mapping_detach(&one);
    plasma_swd_ps_mapping_detach(&two);
    assert(!one.active && !two.active);
    assert(one.native.words == NULL && two.native.words == NULL);
    assert(fcntl(fd, F_GETFD) >= 0); /* borrowed descriptor still valid */
    plasma_swd_owner_lock_release(&l1);
    plasma_swd_owner_lock_release(&l2);
    assert(close(fd) == 0);
    char side[512];
    assert(snprintf(side, sizeof(side), "%s.site-1", lock_path) > 0);
    assert(unlink(side) == 0);
    assert(snprintf(side, sizeof(side), "%s.site-2", lock_path) > 0);
    assert(unlink(side) == 0);
    assert(unlink(lock_path) == 0 && unlink(data) == 0);
    puts("PLASMA_PSNATIVE_MAPPED_FD_HOST_ONLY_PASS");
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only C regression of the PR #1199-inspired 32-bit MMIO provider.
 * All pages are synthetic stack arrays; no physical /dev/mem, Z2 or DUT.
 */
#define _POSIX_C_SOURCE 200809L
#include "../plasma_swd_native_words.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct authority {
    bool boot_ok, image_ok, manifest_ok, voltage_ok, root_ok, live;
    uint64_t generation[2];
    unsigned int checks, invalidations;
};

static int attest(void *ctx, unsigned int site, uint64_t generation)
{
    struct authority *a = ctx;
    a->checks++;
    if (site < 1 || site > 2 || !a->boot_ok || !a->image_ok ||
        !a->manifest_ok || !a->voltage_ok || !a->root_ok || !a->live)
        return -1;
    return a->generation[site - 1] == generation ? 0 : -1;
}

static void revoke(void *ctx)
{
    struct authority *a = ctx;
    a->invalidations++;
    a->live = false;
}

static void set_all(struct authority *a)
{
    memset(a, 0, sizeof(*a));
    a->boot_ok = a->image_ok = a->manifest_ok = true;
    a->voltage_ok = a->root_ok = a->live = true;
    a->generation[0] = 11;
    a->generation[1] = 22;
}

static void test_native_word_access(void)
{
    char name[] = "/tmp/plasma-native-words-lock-XXXXXX";
    int fd = mkstemp(name);
    assert(fd >= 0);
    close(fd);
    struct plasma_swd_owner_lock lock1 = {.fd = -1, .site_fd = -1};
    struct plasma_swd_owner_lock lock2 = {.fd = -1, .site_fd = -1};
    assert(plasma_swd_owner_lock_acquire_site(&lock1, name, 1u) == 0);
    assert(plasma_swd_owner_lock_acquire_site(&lock2, name, 2u) == 0);

    uint32_t page1[1024] = {0}, page2[1024] = {0};
    page1[0] = PLASMA_SWD_ABI_V5 | 1u;
    page2[0] = PLASMA_SWD_ABI_V5 | 2u;
    struct authority a;
    set_all(&a);
    struct plasma_swd_native_words n1, n2;
    assert(plasma_swd_native_words_init(&n1, page1, sizeof(page1),
           &lock1, 1, 11, &a, attest, revoke) == PLASMA_SWD_OK);
    assert(plasma_swd_native_words_init(&n2, page2, sizeof(page2),
           &lock2, 2, 22, &a, attest, revoke) == PLASMA_SWD_OK);
    assert(plasma_swd_native_words_init(&n1, page1, sizeof(page1)-4u,
           &lock1, 1, 11, &a, attest, revoke) == PLASMA_SWD_BAD_ARG);
    assert(plasma_swd_native_words_init(&n1, page1, sizeof(page1),
           &lock2, 1, 11, &a, attest, revoke) == PLASMA_SWD_BAD_ARG);
    struct plasma_swd_lease_word_port lease1, lease2;
    struct plasma_swd_lease_provider p1 = plasma_swd_native_words_provider(&n1);
    struct plasma_swd_lease_provider p2 = plasma_swd_native_words_provider(&n2);
    assert(plasma_swd_lease_word_port_init(
           &lease1, &p1, &lock1, 1, 11) == PLASMA_SWD_OK);
    assert(plasma_swd_lease_word_port_init(
           &lease2, &p2, &lock2, 2, 22) == PLASMA_SWD_OK);
    assert(plasma_swd_lease_word_port_admit(&lease1) == PLASMA_SWD_OK);
    assert(plasma_swd_lease_word_port_admit(&lease2) == PLASMA_SWD_OK);

    struct plasma_swd_word_io io1, io2;
    assert(plasma_swd_lease_word_port_make_io(&lease1, &io1) == 0);
    assert(plasma_swd_lease_word_port_make_io(&lease2, &io2) == 0);
    uint32_t id = 0;
    assert(io1.read32(io1.ctx, PLASMA_SWD_SITE1_BASE, &id) == 0);
    assert(id == PLASMA_SWD_ABI_V5 + 1);
    assert(io2.read32(io2.ctx, PLASMA_SWD_SITE2_BASE, &id) == 0);
    assert(id == PLASMA_SWD_ABI_V5 + 2);
    assert(io1.write32(io1.ctx, PLASMA_SWD_SITE1_BASE + 0x10, 0xA5A55A5Au) == 0);
    assert(io1.write_barrier(io1.ctx) == 0);
    assert(page1[4] == 0xA5A55A5Au && page2[4] == 0);
    assert(io2.write32(io2.ctx, PLASMA_SWD_SITE2_BASE + 0x10, 0x12345678u) == 0);
    assert(io2.write_barrier(io2.ctx) == 0);
    assert(page2[4] == 0x12345678u);
    /* Exercise the actual NORMAL FIFO admission through native C words,
     * without pretending a synthetic file implements FPGA SWD replies. */
    page1[1] = page2[1] = 1u; /* synthetic STATUS bit */
    struct plasma_swd_fifo fifo1, fifo2;
    assert(plasma_swd_fifo_init(&fifo1, &io1, 1, 8) == 0);
    assert(plasma_swd_fifo_init(&fifo2, &io2, 2, 8) == 0);
    assert(plasma_swd_fifo_admit(&fifo1) == 0);
    assert(plasma_swd_fifo_admit(&fifo2) == 0);
    assert(fifo1.admitted && fifo2.admitted);
    assert(page1[0x38/4] == 1 && page2[0x38/4] == 1);
    assert(page1[0x28/4] == 1 && page2[0x28/4] == 1);
    unsigned int before = a.checks;
    assert(io1.read32(io1.ctx, PLASMA_SWD_SITE1_BASE + 0x10, &id) != 0);
    assert(io1.write32(io1.ctx, PLASMA_SWD_SITE2_BASE + 0x10, 1) != 0);
    assert(io1.read32(io1.ctx, PLASMA_SWD_SITE1_BASE + 0x3c, &id) != 0);
    assert(io1.write32(io1.ctx, PLASMA_SWD_SITE1_BASE + 0x40, 1) != 0);
    assert(a.checks == before); /* rejected before touching mapped memory */
    assert(!plasma_swd_native_words_armv7_dmb());

    /* Each access must re-evaluate authority; no cached Root/voltage bit. */
    a.voltage_ok = false;
    assert(io1.write32(io1.ctx, PLASMA_SWD_SITE1_BASE + 0x10, 9) != 0);
    assert(a.invalidations == 1 && !a.live);
    assert(page1[4] == 0xA5A55A5Au);
    assert(io2.read32(io2.ctx, PLASMA_SWD_SITE2_BASE, &id) != 0);
    assert(a.invalidations == 2); /* peer poisoned via shared domain */
    assert(io1.write_barrier(io1.ctx) != 0);

    plasma_swd_native_words_retire(&n1);
    plasma_swd_native_words_retire(&n2);
    plasma_swd_owner_lock_release(&lock1);
    plasma_swd_owner_lock_release(&lock2);
    char buf[512];
    assert(snprintf(buf, sizeof(buf), "%s.site-1", name) > 0);
    assert(unlink(buf) == 0);
    assert(snprintf(buf, sizeof(buf), "%s.site-2", name) > 0);
    assert(unlink(buf) == 0);
    assert(unlink(name) == 0);
}

static void test_fail_closed_wrong_abi_and_expired_lock(void)
{
    char name[] = "/tmp/plasma-native-words-negative-XXXXXX";
    int fd = mkstemp(name);
    assert(fd >= 0);
    close(fd);
    struct plasma_swd_owner_lock lock = {.fd = -1, .site_fd = -1};
    assert(plasma_swd_owner_lock_acquire_site(&lock, name, 1) == 0);
    uint32_t page[1024] = {0};
    page[0] = 0x00040001u; /* stale FPGA ABI */
    struct authority a;
    set_all(&a);
    struct plasma_swd_native_words n;
    assert(plasma_swd_native_words_init(&n, page, sizeof(page), &lock,
           1, 11, &a, attest, revoke) == 0);
    struct plasma_swd_lease_provider provider = plasma_swd_native_words_provider(&n);
    struct plasma_swd_lease_word_port lease;
    assert(plasma_swd_lease_word_port_init(
           &lease, &provider, &lock, 1, 11) == 0);
    assert(plasma_swd_lease_word_port_admit(&lease) == PLASMA_SWD_NOT_READY);
    page[0] = PLASMA_SWD_ABI_V5 | 1;
    assert(plasma_swd_lease_word_port_admit(&lease) == PLASMA_SWD_NOT_READY);
    plasma_swd_owner_lock_release(&lock);
    assert(plasma_swd_native_words_init(&n, page, sizeof(page), &lock,
           1, 11, &a, attest, revoke) == PLASMA_SWD_BAD_ARG);
    char buf[512];
    assert(snprintf(buf, sizeof(buf), "%s.site-1", name) > 0);
    assert(unlink(buf) == 0);
    assert(unlink(name) == 0);
}

int main(void)
{
    test_native_word_access();
    test_fail_closed_wrong_abi_and_expired_lock();
    puts("PLASMA_NATIVE_V5_WORDS_HOST_ONLY_PASS");
    return 0;
}

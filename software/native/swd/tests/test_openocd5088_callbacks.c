/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only binding regression using real C lease/native word port and
 * deliberately synthetic authority, Linux lock and virtual register page.
 * The OpenOCD header is a SHIM; genuine upstream build is separate CI.
 */
#define _POSIX_C_SOURCE 200809L
#include "../plasma_swd_openocd5088_binding.h"
#include <jtag/swd.h>
#include <jtag/interface.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern const struct swd_driver plasma_swd_openocd5088_ops;
extern struct adapter_driver plasma_swd_adapter_driver;

struct synthetic_authority {
    bool boot, root, image, manifest, voltage, current;
    uint64_t generation;
    unsigned int checks, revokes;
};
static int authorize(void *ctx, unsigned int site, uint64_t generation)
{
    struct synthetic_authority *a = ctx;
    a->checks++;
    return (site == 1u && generation == a->generation && a->boot &&
            a->root && a->image && a->manifest && a->voltage && a->current)
        ? 0 : -1;
}
static void revoke(void *ctx)
{
    struct synthetic_authority *a = ctx;
    a->current = false;
    a->revokes++;
}

int main(void)
{
    char path[] = "/tmp/plasma-bind-guarded-XXXXXX";
    int fd = mkstemp(path);
    assert(fd >= 0);
    close(fd);

    struct plasma_swd_owner_lock lock = {.fd = -1, .site_fd = -1};
    assert(plasma_swd_owner_lock_acquire_site(&lock, path, 1u) == 0);
    uint32_t page[1024] = {0};
    page[0] = PLASMA_SWD_ABI_V5 | 1u;
    page[0x04/4] = 1u; /* synthetic enabled status */
    struct synthetic_authority a = {
        .boot = true, .root = true, .image = true, .manifest = true,
        .voltage = true, .current = true, .generation = 11u,
    };
    struct plasma_swd_native_words native;
    assert(plasma_swd_native_words_init(
        &native, page, sizeof(page), &lock, 1u, 11u,
        &a, authorize, revoke) == PLASMA_SWD_OK);
    struct plasma_swd_lease_provider provider =
        plasma_swd_native_words_provider(&native);
    struct plasma_swd_lease_word_port lease;
    assert(plasma_swd_lease_word_port_init(
        &lease, &provider, &lock, 1u, 11u) == PLASMA_SWD_OK);
    assert(plasma_swd_lease_word_port_admit(&lease) == PLASMA_SWD_OK);
    struct plasma_swd_word_io io = {0};
    assert(plasma_swd_lease_word_port_make_io(&lease, &io) == 0);
    struct plasma_swd_fifo site;
    assert(plasma_swd_fifo_init(&site, &io, 1u, 10u) == PLASMA_SWD_OK);
    assert(plasma_swd_fifo_admit(&site) == PLASMA_SWD_OK);

    /* A naked admitted bit or an arbitrary fake IO object is insufficient. */
    struct plasma_swd_fifo untrusted = site;
    untrusted.io.ctx = page;
    assert(plasma_swd_openocd5088_ops.init() == ERROR_OK);
    assert(plasma_swd_adapter_driver.init() == ERROR_FAIL);
    assert(plasma_swd_openocd5088_bind_guarded(
        &untrusted, &lease, &native) == ERROR_FAIL);
    struct plasma_swd_native_words alternate = native;
    assert(plasma_swd_openocd5088_bind_guarded(
        &site, &lease, &alternate) == ERROR_FAIL);
    assert(plasma_swd_openocd5088_bind_guarded(
        &site, &lease, &native) == ERROR_OK);
    assert(plasma_swd_openocd5088_bind_guarded(
        &site, &lease, &native) == ERROR_FAIL);
    assert(plasma_swd_adapter_driver.init() == ERROR_OK);

    /* Synthetic ACK/data prepared in page; this is NOT a virtual
     * electrically measured SWD target or a Flash proof. */
    page[0x24/4] = 2u; /* RX FIFO nonempty */
    page[0x18/4] = (1u << 16) | (1u << 4) | 0x80u;
    page[0x1c/4] = 0x1BA01477u;
    uint32_t got = 0;
    assert(plasma_swd_openocd5088_ops.read_reg(0x24, &got, 0) == ERROR_OK);
    assert(plasma_swd_openocd5088_ops.run() == ERROR_OK);
    assert(got == 0x1BA01477u);

    assert(plasma_swd_openocd5088_ops.write_reg(0x3Au, 123u, 0) == ERROR_OK);
    uint32_t push = page[0x14/4];
    /* Image/voltage revocation occurs AFTER queue, BEFORE run. */
    a.voltage = false;
    assert(plasma_swd_openocd5088_owner_ready() == ERROR_FAIL);
    assert(plasma_swd_openocd5088_ops.run() == ERROR_FAIL);
    assert(site.blocked && site.count == 0u && !site.admitted);
    assert(page[0x14/4] == push); /* queued write was never pushed */
    assert(plasma_swd_adapter_driver.init() == ERROR_FAIL);
    assert(plasma_swd_openocd5088_ops.init() == ERROR_OK);

    assert(plasma_swd_adapter_driver.quit() == ERROR_OK);
    assert(plasma_swd_openocd5088_owner_ready() == ERROR_FAIL);
    /* Fail-closed: even restoring authorization cannot revive a
     * previously bound session; explicit fresh owner/image admission.
     */
    a.voltage = true;
    assert(plasma_swd_openocd5088_bind_guarded(
        &site, &lease, &native) == ERROR_FAIL);
    plasma_swd_native_words_retire(&native);
    plasma_swd_owner_lock_release(&lock);
    char site_path[512];
    assert(snprintf(site_path, sizeof(site_path), "%s.site-1", path) > 0);
    assert(unlink(site_path) == 0);
    assert(unlink(path) == 0);
    puts("PLASMA_OPENOCD5088_CALLBACK_SHIM_HOST_ONLY_PASS");
    return 0;
}

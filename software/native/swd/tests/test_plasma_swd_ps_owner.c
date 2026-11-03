/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only PS owner contract test. Fixture files stand in for /proc, sysfs,
 * the Root journal and /dev/mem; this is NOT Z2 or DUT evidence.
 * usage: test_plasma_swd_ps_owner <empty-temp-dir>
 */
#define _GNU_SOURCE
#include "plasma_swd_openocd5088_ps_owner.h"
#include "plasma_swd_openocd5088_binding.h"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)

static char root[200];
static struct plasma_swd_ps_paths P;
static const char *BOOT = "4cefdc0c-f586-4d19-b126-1d8e1108c8f1";
static const char *MAN = "f470a4fac8accd0b1fcfb50243d4d663e1ddee209bc1c506e8e587c1f5ff859c";
static const char *FW = "d3b65a818c03ef1f73a3f0026357d6ed6a9fd903f2f041bc09b89d6b6ba3b773";
static const char *SID = "fpga-e412210dbd8e4d49b54f043ea697cb21";
static const char *IMG = "z2-independent-swd-v5-bd976140";

static void path(char *out, const char *name)
{
    snprintf(out, 256, "%s/%s", root, name);
}

static int put(const char *p, const char *text, mode_t mode)
{
    unlink(p);
    int fd = open(p, O_CREAT | O_WRONLY | O_TRUNC, mode);
    if (fd < 0)
        return -1;
    ssize_t n = write(fd, text, strlen(text));
    close(fd);
    chmod(p, mode);
    return n == (ssize_t)strlen(text) ? 0 : -1;
}

static void journal_text(char *buf, size_t cap, const char *status)
{
    snprintf(buf, cap,
             "{\"boot_id\":\"%s\",\"download_count\":1,\"firmware_sha256\":\"%s\","
             "\"image\":\"plasma-swd-independent-bd976140.bin\",\"image_id\":\"%s\","
             "\"manifest_sha256\":\"%s\",\"session_id\":\"%s\",\"status\":\"%s\"}\n",
             BOOT, FW, IMG, MAN, SID, status);
}

static int make_devmem(uint32_t status)
{
    int fd = open(P.devmem, O_CREAT | O_RDWR | O_TRUNC, 0600);
    if (fd < 0 || ftruncate(fd, 0x43C03000) != 0)
        return -1;
    uint32_t id = 0x00050001u;
    int ok = pwrite(fd, &id, 4, 0x43C01000) == 4 &&
             pwrite(fd, &status, 4, 0x43C01004) == 4;
    close(fd);
    return ok ? 0 : -1;
}

static uint32_t devmem_word(uint32_t off)
{
    uint32_t v = 0xFFFFFFFFu;
    int fd = open(P.devmem, O_RDONLY);
    if (fd >= 0) {
        if (pread(fd, &v, 4, 0x43C01000 + off) != 4)
            v = 0xFFFFFFFFu;
        close(fd);
    }
    return v;
}

static int setup(void)
{
    char j[1024], boot[64];
    path(P.boot_id, "boot_id");
    path(P.manager_state, "state");
    path(P.root_journal, "journal.json");
    path(P.lock, "plasma-mmio.lock");
    path(P.devmem, "devmem");
    snprintf(boot, sizeof(boot), "%s\n", BOOT);
    journal_text(j, sizeof(j), "IMAGE");
    if (put(P.boot_id, boot, 0644) || put(P.manager_state, "operating\n", 0644) ||
        put(P.root_journal, j, 0600))
        return -1;
    plasma_swd_ps_owner_set_paths_for_host_test(&P);
    return 0;
}

int main(int argc, char **argv)
{
    char why[96], j[1024];
    CHECK(argc == 2);
    snprintf(root, sizeof(root), "%s", argv[1]);
    CHECK(setup() == 0);

    /* No Site selected => fail closed before any MMIO. */
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_SITE_NOT_SELECTED") == 0);
    CHECK(plasma_swd_ps_owner_select_site(3) != PLASMA_SWD_OK);
    CHECK(plasma_swd_ps_owner_select_site(1) == PLASMA_SWD_OK);
    CHECK(make_devmem(0x11u) == 0);

    /* PL not holding a loaded Image (manager / journal / boot) => no MMIO:
     * an access to an absent AXI slave could hang the bus. */
    CHECK(put(P.manager_state, "unknown\n", 0644) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_PL_IMAGE_NOT_LOADED") == 0);
    CHECK(put(P.manager_state, "operating\n", 0644) == 0);
    journal_text(j, sizeof(j), "RECOVERY");
    CHECK(put(P.root_journal, j, 0600) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_PL_IMAGE_NOT_LOADED") == 0);
    journal_text(j, sizeof(j), "IMAGE");
    CHECK(put(P.root_journal, j, 0644) == 0); /* not root-private */
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(put(P.root_journal, j, 0600) == 0);
    CHECK(put(P.boot_id, "00000000-0000-0000-0000-000000000000\n", 0644) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_PL_IMAGE_NOT_LOADED") == 0);
    CHECK(devmem_word(0x38) == 0u); /* MODE untouched */
    char boot[64];
    snprintf(boot, sizeof(boot), "%s\n", BOOT);
    CHECK(put(P.boot_id, boot, 0644) == 0);

    /* Loaded Image, no admission record, no electrical file => attach. */
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) == PLASMA_SWD_OK);
    CHECK(devmem_word(0x38) == 1u && devmem_word(0x28) == 1u);
    CHECK(plasma_swd_openocd5088_owner_ready() == 0);
    /* Hot path does no file I/O: later file changes do not revoke words. */
    CHECK(put(P.boot_id, "00000000-0000-0000-0000-000000000000\n", 0644) == 0);
    CHECK(plasma_swd_openocd5088_owner_ready() == 0);
    CHECK(put(P.boot_id, boot, 0644) == 0);
    /* Second attach in the same process is refused. */
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_ALREADY_ATTACHED") == 0);

    /* A regular file cannot emulate CONTROL acknowledgement, so safe-off
     * must stop after CONTROL=0 and NOT write MODE=0. */
    CHECK(plasma_swd_ps_owner_safe_off(why, sizeof(why)) == PLASMA_SWD_IO_UNCERTAIN);
    CHECK(devmem_word(0x28) == 0u && devmem_word(0x38) == 1u);
    CHECK(strcmp(why, "SAFE_OFF_UNCERTAIN") == 0);
    plasma_swd_openocd5088_unbind();
    plasma_swd_ps_owner_detach();

    /* Fresh session: stale MODE=NORMAL whose OFF cannot be proven => the
     * Site is left as is and attach is refused. */
    CHECK(plasma_swd_ps_owner_select_site(1) == PLASMA_SWD_OK);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_STALE_SITE_NOT_RECOVERABLE") == 0);
    CHECK(devmem_word(0x38) == 1u);

    puts("PLASMA_SWD_PS_OWNER_HOST_ONLY_PASS");
    return 0;
}

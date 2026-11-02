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
static const char *PIN = "61e2137c4ecb92bcabd579fbb28349347de05c60";
static const char *MAN = "f470a4fac8accd0b1fcfb50243d4d663e1ddee209bc1c506e8e587c1f5ff859c";
static const char *FW = "d3b65a818c03ef1f73a3f0026357d6ed6a9fd903f2f041bc09b89d6b6ba3b773";
static const char *SID = "fpga-e412210dbd8e4d49b54f043ea697cb21";
static const char *IMG = "z2-independent-swd-v5-ab79b04e";

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
             "\"image\":\"plasma-swd-independent-ab79b04e.bin\",\"image_id\":\"%s\","
             "\"manifest_sha256\":\"%s\",\"session_id\":\"%s\",\"status\":\"%s\"}\n",
             BOOT, FW, IMG, MAN, SID, status);
}

static int write_record(unsigned int site, long long rec_exp, long long el_exp,
                        int voltage)
{
    struct stat js, es;
    char rec[4096], p[320];
    if (stat(P.root_journal, &js))
        return -1;
    char el[256];
    path(el, "elec-site1.json");
    if (stat(el, &es))
        return -1;
    snprintf(rec, sizeof(rec),
             "schema=plasma.swd.ps-admission.v1\nsite_id=%u\nboot_id=%s\n"
             "root_source_commit=%s\nimage_manifest_sha256=%s\n"
             "loaded_image_sha256=%s\nimage_id=%s\nroot_image_session_id=%s\n"
             "abi_version=5\nsite_bitmap=3\nroot_source_pinned=1\n"
             "manager_operating=1\nactive_image_attested=1\n"
             "axi_isolation_proven=1\nowner_scan_complete=1\n"
             "voltage_qualified=%d\nrecovery_available=1\njournal_dev=%llu\n"
             "journal_ino=%llu\njournal_size=%llu\njournal_mtime_ns=%lld\n"
             "electrical_path=%s\nelectrical_ino=%llu\nelectrical_mtime_ns=%lld\n"
             "electrical_expires_epoch=%lld\nrecord_expires_epoch=%lld\n",
             site, BOOT, PIN, MAN, FW, IMG, SID, voltage,
             (unsigned long long)js.st_dev, (unsigned long long)js.st_ino,
             (unsigned long long)js.st_size,
             (long long)js.st_mtim.tv_sec * 1000000000LL + js.st_mtim.tv_nsec,
             el, (unsigned long long)es.st_ino,
             (long long)es.st_mtim.tv_sec * 1000000000LL + es.st_mtim.tv_nsec,
             el_exp, rec_exp);
    snprintf(p, sizeof(p), "%s/swd-site%u-admission", P.record_dir, site);
    return put(p, rec, 0600);
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
    char j[1024];
    path(P.boot_id, "boot_id");
    path(P.manager_state, "state");
    path(P.root_journal, "journal.json");
    path(P.root_pin, "pin");
    path(P.record_dir, "run");
    path(P.lock, "plasma-mmio.lock");
    path(P.devmem, "devmem");
    mkdir(P.record_dir, 0700);
    char el[256];
    path(el, "elec-site1.json");
    char pin[64];
    snprintf(pin, sizeof(pin), "%s\n", PIN);
    char boot[64];
    snprintf(boot, sizeof(boot), "%s\n", BOOT);
    journal_text(j, sizeof(j), "IMAGE");
    if (put(P.boot_id, boot, 0644) || put(P.manager_state, "operating\n", 0644) ||
        put(P.root_journal, j, 0600) || put(P.root_pin, pin, 0644) ||
        put(el, "{\"method\":\"OWNER_ONSITE_ATTESTATION\"}\n", 0600))
        return -1;
    plasma_swd_ps_owner_set_paths_for_host_test(&P);
    return 0;
}

static long long now_s(void) { return (long long)time(NULL); }

int main(int argc, char **argv)
{
    char why[96];
    struct plasma_swd_ps_admission a;
    CHECK(argc == 2);
    snprintf(root, sizeof(root), "%s", argv[1]);
    CHECK(setup() == 0);

    /* Parser: exact keys only, every line terminated. */
    CHECK(plasma_swd_ps_admission_parse("schema=x\n", 9, &a) != PLASMA_SWD_OK);
    CHECK(plasma_swd_ps_admission_parse("", 0, &a) != PLASMA_SWD_OK);

    /* No Site selected / no record => fail closed before any MMIO. */
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_SITE_NOT_SELECTED") == 0);
    CHECK(plasma_swd_ps_owner_select_site(3) != PLASMA_SWD_OK);
    CHECK(plasma_swd_ps_owner_select_site(1) == PLASMA_SWD_OK);
    CHECK(make_devmem(0x11u) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_ADMISSION_RECORD_INVALID") == 0);
    CHECK(devmem_word(0x38) == 0u); /* MODE untouched */

    /* Voltage not attested => evidence incomplete, no MMIO. */
    CHECK(write_record(1, now_s() + 600, now_s() + 600, 0) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_EVIDENCE_INCOMPLETE") == 0);
    CHECK(devmem_word(0x38) == 0u);

    /* Expired electrical attestation => live facts denied. */
    CHECK(write_record(1, now_s() + 600, now_s() - 1, 1) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_LIVE_FACTS_DENIED") == 0);

    /* Journal no longer IMAGE (e.g. Root restore) => denied. */
    char j[1024];
    journal_text(j, sizeof(j), "RECOVERY");
    CHECK(put(P.root_journal, j, 0600) == 0);
    CHECK(write_record(1, now_s() + 600, now_s() + 600, 1) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_LIVE_FACTS_DENIED") == 0);

    /* Valid admission => attach, MODE=NORMAL, CONTROL=1 written. */
    journal_text(j, sizeof(j), "IMAGE");
    CHECK(put(P.root_journal, j, 0600) == 0);
    CHECK(write_record(1, now_s() + 600, now_s() + 600, 1) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) == PLASMA_SWD_OK);
    CHECK(devmem_word(0x38) == 1u && devmem_word(0x28) == 1u);
    CHECK(plasma_swd_openocd5088_owner_ready() == 0);

    /* Live boot change => every subsequent access revoked. */
    CHECK(put(P.boot_id, "00000000-0000-0000-0000-000000000000\n", 0644) == 0);
    CHECK(plasma_swd_openocd5088_owner_ready() != 0);
    char boot[64];
    snprintf(boot, sizeof(boot), "%s\n", BOOT);
    CHECK(put(P.boot_id, boot, 0644) == 0);
    CHECK(plasma_swd_openocd5088_owner_ready() != 0); /* terminal */

    /* Revoked live evidence => safe-off performs NO MMIO at all. */
    CHECK(plasma_swd_ps_owner_safe_off(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(devmem_word(0x28) == 1u && devmem_word(0x38) == 1u);
    CHECK(strcmp(why, "SAFE_OFF_UNCERTAIN") == 0);
    plasma_swd_openocd5088_unbind();
    plasma_swd_ps_owner_detach();

    /* Fresh session: stale MODE=NORMAL whose OFF cannot be proven => the
     * Site is left as is and attach is refused. */
    CHECK(plasma_swd_ps_owner_select_site(1) == PLASMA_SWD_OK);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK);
    CHECK(strcmp(why, "PS_OWNER_STALE_SITE_NOT_RECOVERABLE") == 0);
    CHECK(devmem_word(0x38) == 1u);

    /* Clean session; a regular file cannot emulate CONTROL acknowledgement,
     * so safe-off must stop after CONTROL=0 and NOT write MODE=0. */
    CHECK(make_devmem(0x11u) == 0);
    CHECK(plasma_swd_ps_owner_attach(why, sizeof(why)) == PLASMA_SWD_OK);
    CHECK(plasma_swd_ps_owner_safe_off(why, sizeof(why)) == PLASMA_SWD_IO_UNCERTAIN);
    CHECK(devmem_word(0x28) == 0u && devmem_word(0x38) == 1u);
    CHECK(strcmp(why, "SAFE_OFF_UNCERTAIN") == 0);
    plasma_swd_openocd5088_unbind();
    plasma_swd_ps_owner_detach();

    puts("PLASMA_SWD_PS_OWNER_HOST_ONLY_PASS");
    return 0;
}

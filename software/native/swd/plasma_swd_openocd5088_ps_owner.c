/* SPDX-License-Identifier: GPL-2.0-or-later
 * PS-local ABI-v5 Site owner for source-locked OpenOCD 5088db4c.
 * See plasma_swd_openocd5088_ps_owner.h for the boundary.
 */
#define _GNU_SOURCE
#include "plasma_swd_openocd5088_ps_owner.h"
#include "plasma_swd_openocd5088_binding.h"
#include "plasma_swd_ps_mapping.h"
#include "plasma_swd_fifo_core.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef PLASMA_SWD_HOST_TEST
#define TRUSTED_UID geteuid() /* Host-only: unprivileged test fixtures */
#else
#define TRUSTED_UID 0u
#endif

/* Read a small file fully. If private_root, require regular, uid 0, no
 * group/other permission bits and no symlink. */
static int read_file(const char *path, char *buf, size_t cap, size_t *len,
                     bool private_root, bool root_owned, struct stat *out)
{
    struct stat st;
    if (lstat(path, &st) != 0)
        return -1;
    if (root_owned && (!S_ISREG(st.st_mode) || st.st_uid != TRUSTED_UID ||
                       (st.st_mode & 0022)))
        return -1;
    if (private_root && (st.st_mode & 0077))
        return -1;
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    size_t total = 0;
    for (;;) {
        if (total + 1 >= cap) { /* too large */
            close(fd);
            return -1;
        }
        ssize_t n = read(fd, buf + total, cap - 1 - total);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            close(fd);
            return -1;
        }
        if (n == 0)
            break;
        total += (size_t)n;
    }
    close(fd);
    buf[total] = '\0';
    *len = total;
    if (out)
        *out = st;
    return 0;
}

static bool contains_kv(const char *json, const char *key, const char *value)
{
    char needle[200];
    int n = snprintf(needle, sizeof(needle), "\"%s\":\"%s\"", key, value);
    return n > 0 && (size_t)n < sizeof(needle) && strstr(json, needle) != NULL;
}

void plasma_swd_ps_default_paths(struct plasma_swd_ps_paths *p)
{
    memset(p, 0, sizeof(*p));
    strcpy(p->boot_id, "/proc/sys/kernel/random/boot_id");
    strcpy(p->manager_state, "/sys/class/fpga_manager/fpga0/state");
    strcpy(p->root_journal,
           "/var/lib/plasma-privileged/fpga-deployment-state.json");
    strcpy(p->lock, PLASMA_SWD_MMIO_OWNER_LOCK);
    strcpy(p->devmem, "/dev/mem");
}

static struct {
    unsigned int site;
    bool attached;
    int fd;
    struct plasma_swd_ps_paths paths;
    struct plasma_swd_owner_lock lock;
    struct plasma_swd_ps_mapping mapping;
    struct plasma_swd_lease_word_port lease;
    struct plasma_swd_fifo fifo;
    bool paths_overridden;
    struct plasma_swd_ps_paths override;
} g = {.fd = -1};

/* FPGA Manager operating and the root-private Root journal says this boot
 * holds a loaded Image. Policy (which Image, who may program, DUT supply
 * conditions) belongs to the caller, not to the adapter. */
static int pl_image_loaded(void)
{
    char buf[PLASMA_SWD_PS_JOURNAL_MAX], boot[64];
    size_t len = 0, blen = 0;
    if (read_file(g.paths.manager_state, buf, sizeof(buf), &len, false, false, NULL) ||
        strncmp(buf, "operating", 9) != 0 || (buf[9] != '\n' && buf[9] != '\0'))
        return -1;
    if (read_file(g.paths.boot_id, boot, sizeof(boot), &blen, false, false, NULL))
        return -1;
    while (blen && (boot[blen - 1] == '\n' || boot[blen - 1] == ' '))
        boot[--blen] = '\0';
    if (blen != 36)
        return -1;
    if (read_file(g.paths.root_journal, buf, sizeof(buf), &len, true, true, NULL))
        return -1;
    return contains_kv(buf, "status", "IMAGE") &&
           contains_kv(buf, "boot_id", boot) ? 0 : -1;
}

/* Per-word authority: memory-only. The held Site lock + reload fence is
 * what keeps PL stable; no file I/O on the MMIO hot path. */
static int site_held(void *ctx, unsigned int site, uint64_t generation)
{
    (void)generation;
    return ctx == &g && site == g.site &&
           plasma_swd_owner_lock_valid(&g.lock) ? 0 : -1;
}

static void site_release(void *ctx)
{
    (void)ctx;
}

#ifdef PLASMA_SWD_HOST_TEST
void plasma_swd_ps_owner_set_paths_for_host_test(
    const struct plasma_swd_ps_paths *paths)
{
    g.override = *paths;
    g.paths_overridden = true;
}
#endif

int plasma_swd_ps_owner_select_site(unsigned int site_id)
{
    if (g.attached || (site_id != 1u && site_id != 2u))
        return PLASMA_SWD_BAD_ARG;
    g.site = site_id;
    return PLASMA_SWD_OK;
}

unsigned int plasma_swd_ps_owner_selected_site(void)
{
    return g.site;
}

static void set_err(char *err, size_t len, const char *msg)
{
    if (err && len)
        snprintf(err, len, "%s", msg);
}

static void release_all(void)
{
    plasma_swd_ps_mapping_detach(&g.mapping);
    if (g.fd >= 0)
        close(g.fd);
    g.fd = -1;
    plasma_swd_owner_lock_release(&g.lock);
    g.attached = false;
}

int plasma_swd_ps_owner_attach(char *err, size_t err_len)
{
    if (g.attached) {
        set_err(err, err_len, "PS_OWNER_ALREADY_ATTACHED");
        return PLASMA_SWD_NOT_READY;
    }
    if (g.site != 1u && g.site != 2u) {
        set_err(err, err_len, "PS_OWNER_SITE_NOT_SELECTED");
        return PLASMA_SWD_BAD_ARG;
    }
    memset(&g.mapping, 0, sizeof(g.mapping));
    memset(&g.lease, 0, sizeof(g.lease));
    memset(&g.fifo, 0, sizeof(g.fifo));
    struct plasma_swd_owner_lock fresh = {.fd = -1, .site_fd = -1};
    fresh.epoch = g.lock.epoch;
    g.lock = fresh;
    if (g.paths_overridden)
        g.paths = g.override;
    else
        plasma_swd_ps_default_paths(&g.paths);
#ifndef PLASMA_SWD_HOST_TEST
    if (geteuid() != 0) {
        set_err(err, err_len, "PS_OWNER_ROOT_REQUIRED");
        return PLASMA_SWD_NOT_READY;
    }
#endif
    /* Lock FIRST: from here the Root Loader cannot take the reload fence. */
    if (plasma_swd_owner_lock_acquire_site(&g.lock, g.paths.lock, g.site)) {
        set_err(err, err_len, "PS_OWNER_SITE_LOCK_UNAVAILABLE");
        return PLASMA_SWD_NOT_READY;
    }
    /* Once, before the first MMIO: PL must hold a Root-loaded Image in this
     * boot, otherwise a Site-page access may hang the AXI bus. The Site
     * lock (reload fence) keeps it loaded for the whole session. */
    if (pl_image_loaded() != 0) {
        set_err(err, err_len, "PS_OWNER_PL_IMAGE_NOT_LOADED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
#ifdef PLASMA_SWD_HOST_TEST
    g.fd = open(g.paths.devmem, O_RDWR | O_CLOEXEC);
#else
    g.fd = open(g.paths.devmem, O_RDWR | O_SYNC | O_CLOEXEC);
#endif
    if (g.fd < 0) {
        set_err(err, err_len, "PS_OWNER_DEVMEM_OPEN_FAILED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    if (plasma_swd_ps_mapping_attach(&g.mapping, g.fd, &g.lock, g.site, 1u,
                                     &g, site_held, site_release)) {
        set_err(err, err_len, "PS_OWNER_MAPPING_DENIED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    const struct plasma_swd_lease_provider provider =
        plasma_swd_native_words_provider(&g.mapping.native);
    if (plasma_swd_lease_word_port_init(&g.lease, &provider, &g.lock,
                                        g.site, 1u) ||
        plasma_swd_lease_word_port_admit(&g.lease)) {
        set_err(err, err_len, "PS_OWNER_LEASE_OR_SITE_ID_DENIED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    struct plasma_swd_word_io io;
    if (plasma_swd_lease_word_port_make_io(&g.lease, &io) ||
        plasma_swd_fifo_init(&g.fifo, &io, g.site, 20000u)) {
        set_err(err, err_len, "PS_OWNER_FIFO_INIT_DENIED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    int recovered = 0;
    if (plasma_swd_fifo_recover_off(&g.fifo, &recovered) != PLASMA_SWD_OK) {
        /* Busy, invalid mode or uncertain MMIO: leave the Site untouched. */
        set_err(err, err_len, "PS_OWNER_STALE_SITE_NOT_RECOVERABLE");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    int rc = plasma_swd_fifo_admit(&g.fifo);
    if (rc) {
        /* MODE may already be NORMAL: uncertain; no further MMIO. */
        set_err(err, err_len, rc == PLASMA_SWD_NOT_READY
                ? "PS_OWNER_SITE_NOT_OFF_OR_ID_MISMATCH"
                : "PS_OWNER_SITE_ENABLE_UNCERTAIN");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    if (plasma_swd_openocd5088_bind_guarded(&g.fifo, &g.lease,
                                            &g.mapping.native)) {
        set_err(err, err_len, "PS_OWNER_BIND_DENIED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    g.attached = true;
    set_err(err, err_len, recovered ? "PS_OWNER_ATTACHED_AFTER_STALE_OFF"
                                    : "PS_OWNER_ATTACHED");
    return PLASMA_SWD_OK;
}

int plasma_swd_ps_owner_safe_off(char *err, size_t err_len)
{
    int recovered = 0;
    if (!g.attached) {
        set_err(err, err_len, "SAFE_OFF_SKIPPED_NOT_ATTACHED");
        return PLASMA_SWD_NOT_READY;
    }
    /* Still under this process's Site lock. The FIFO may
     * be software-blocked after a failed transfer; the hardware state is
     * what decides: not busy -> discard (never replay) and switch OFF. */
    const int rc = plasma_swd_fifo_recover_off(&g.fifo, &recovered);
    if (rc != PLASMA_SWD_OK) {
        set_err(err, err_len, rc == PLASMA_SWD_IO_UNCERTAIN
                ? "SAFE_OFF_UNCERTAIN" : "SAFE_OFF_SKIPPED_SITE_BUSY_OR_INVALID");
        return rc;
    }
    set_err(err, err_len, "SAFE_OFF_MODE_OFF_VERIFIED");
    return PLASMA_SWD_OK;
}

void plasma_swd_ps_owner_detach(void)
{
    plasma_swd_lease_word_port_retire(&g.lease);
    release_all();
}

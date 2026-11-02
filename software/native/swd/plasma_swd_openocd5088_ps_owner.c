/* SPDX-License-Identifier: GPL-2.0-or-later
 * PS-local ABI-v5 Site owner for source-locked OpenOCD 5088db4c.
 * See plasma_swd_openocd5088_ps_owner.h for the trust boundary.
 */
#define _GNU_SOURCE
#include "plasma_swd_openocd5088_ps_owner.h"
#include "plasma_swd_openocd5088_binding.h"
#include "plasma_swd_ps_mapping.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>


#ifdef PLASMA_SWD_HOST_TEST
#define TRUSTED_UID geteuid() /* Host-only: unprivileged test fixtures */
#else
#define TRUSTED_UID 0u
#endif

/* ------------------------------------------------------------------ */
/* Record parsing (pure)                                               */
/* ------------------------------------------------------------------ */

static const char *const KEYS[] = {
    "schema", "site_id", "boot_id", "root_source_commit",
    "image_manifest_sha256", "loaded_image_sha256", "image_id",
    "root_image_session_id", "abi_version", "site_bitmap",
    "root_source_pinned", "manager_operating", "active_image_attested",
    "axi_isolation_proven", "owner_scan_complete", "voltage_qualified",
    "recovery_available", "journal_dev", "journal_ino", "journal_size",
    "journal_mtime_ns", "electrical_path", "electrical_ino",
    "electrical_mtime_ns", "electrical_expires_epoch",
    "record_expires_epoch",
};
#define NKEYS (sizeof(KEYS) / sizeof(KEYS[0]))
#define SCHEMA "plasma.swd.ps-admission.v1"

static bool copy_str(char *dst, size_t cap, const char *v, size_t vlen)
{
    if (vlen == 0 || vlen >= cap)
        return false;
    memcpy(dst, v, vlen);
    dst[vlen] = '\0';
    return true;
}

static bool parse_u64(const char *v, size_t vlen, uint64_t *out)
{
    char buf[32];
    if (vlen == 0 || vlen >= sizeof(buf))
        return false;
    for (size_t i = 0; i < vlen; ++i)
        if (v[i] < '0' || v[i] > '9')
            return false;
    memcpy(buf, v, vlen);
    buf[vlen] = '\0';
    errno = 0;
    char *end = NULL;
    unsigned long long x = strtoull(buf, &end, 10);
    if (errno || !end || *end)
        return false;
    *out = (uint64_t)x;
    return true;
}

static bool parse_flag(const char *v, size_t vlen, bool *out)
{
    if (vlen != 1 || (v[0] != '0' && v[0] != '1'))
        return false;
    *out = v[0] == '1';
    return true;
}

int plasma_swd_ps_admission_parse(const char *text, size_t len,
                                  struct plasma_swd_ps_admission *a)
{
    bool seen[NKEYS] = {false};
    if (!text || !a || len == 0 || len >= PLASMA_SWD_PS_RECORD_MAX ||
        memchr(text, '\0', len))
        return PLASMA_SWD_BAD_ARG;
    memset(a, 0, sizeof(*a));
    size_t pos = 0;
    while (pos < len) {
        const char *line = text + pos;
        const char *nl = memchr(line, '\n', len - pos);
        if (!nl)
            return PLASMA_SWD_BAD_ARG; /* every line newline-terminated */
        size_t llen = (size_t)(nl - line);
        pos += llen + 1;
        const char *eq = memchr(line, '=', llen);
        if (!eq)
            return PLASMA_SWD_BAD_ARG;
        size_t klen = (size_t)(eq - line);
        const char *v = eq + 1;
        size_t vlen = llen - klen - 1;
        size_t k;
        for (k = 0; k < NKEYS; ++k)
            if (strlen(KEYS[k]) == klen && memcmp(KEYS[k], line, klen) == 0)
                break;
        if (k == NKEYS || seen[k])
            return PLASMA_SWD_BAD_ARG;
        seen[k] = true;
        uint64_t n = 0;
        bool ok = true;
        struct plasma_swd_observed_identity *id = &a->identity;
        switch (k) {
        case 0: ok = vlen == strlen(SCHEMA) && memcmp(v, SCHEMA, vlen) == 0; break;
        case 1: ok = parse_u64(v, vlen, &n) && (n == 1 || n == 2);
            a->site_id = (unsigned int)n; break;
        case 2: ok = copy_str(id->boot_id, sizeof(id->boot_id), v, vlen); break;
        case 3: ok = copy_str(id->root_source_commit,
                              sizeof(id->root_source_commit), v, vlen); break;
        case 4: ok = copy_str(id->image_manifest_sha256,
                              sizeof(id->image_manifest_sha256), v, vlen); break;
        case 5: ok = copy_str(id->loaded_image_sha256,
                              sizeof(id->loaded_image_sha256), v, vlen) &&
                     copy_str(a->firmware_sha256, sizeof(a->firmware_sha256),
                              v, vlen); break;
        case 6: ok = copy_str(id->image_id, sizeof(id->image_id), v, vlen); break;
        case 7: ok = copy_str(id->root_image_session_id,
                              sizeof(id->root_image_session_id), v, vlen); break;
        case 8: ok = parse_u64(v, vlen, &n) && n == 5;
            id->abi_version = (unsigned int)n; break;
        case 9: ok = parse_u64(v, vlen, &n) && n > 0 && n <= 0xFFu;
            id->site_bitmap = (uint32_t)n; break;
        case 10: ok = parse_flag(v, vlen, &id->root_source_pinned); break;
        case 11: ok = parse_flag(v, vlen, &id->manager_operating); break;
        case 12: ok = parse_flag(v, vlen, &id->active_image_attested); break;
        case 13: ok = parse_flag(v, vlen, &id->axi_isolation_proven); break;
        case 14: ok = parse_flag(v, vlen, &id->owner_scan_complete); break;
        case 15: ok = parse_flag(v, vlen, &id->voltage_qualified); break;
        case 16: ok = parse_flag(v, vlen, &id->recovery_available); break;
        case 17: ok = parse_u64(v, vlen, &a->journal_dev); break;
        case 18: ok = parse_u64(v, vlen, &a->journal_ino); break;
        case 19: ok = parse_u64(v, vlen, &a->journal_size); break;
        case 20: ok = parse_u64(v, vlen, &n) && n <= INT64_MAX;
            a->journal_mtime_ns = (int64_t)n; break;
        case 21: ok = copy_str(a->electrical_path, sizeof(a->electrical_path),
                               v, vlen) && v[0] == '/'; break;
        case 22: ok = parse_u64(v, vlen, &a->electrical_ino); break;
        case 23: ok = parse_u64(v, vlen, &n) && n <= INT64_MAX;
            a->electrical_mtime_ns = (int64_t)n; break;
        case 24: ok = parse_u64(v, vlen, &n) && n <= INT64_MAX;
            a->electrical_expires_epoch = (int64_t)n; break;
        case 25: ok = parse_u64(v, vlen, &n) && n <= INT64_MAX;
            a->record_expires_epoch = (int64_t)n; break;
        default: ok = false;
        }
        if (!ok)
            return PLASMA_SWD_BAD_ARG;
    }
    for (size_t k = 0; k < NKEYS; ++k)
        if (!seen[k])
            return PLASMA_SWD_BAD_ARG;
    return PLASMA_SWD_OK;
}

/* ------------------------------------------------------------------ */
/* Live measurement                                                    */
/* ------------------------------------------------------------------ */

static int64_t real_now(void)
{
    return (int64_t)time(NULL);
}

static int64_t mtime_ns(const struct stat *st)
{
    return (int64_t)st->st_mtim.tv_sec * 1000000000LL + st->st_mtim.tv_nsec;
}

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

int plasma_swd_ps_read_live(void *opaque, struct plasma_swd_observed_identity *live)
{
    struct plasma_swd_ps_live_ctx *c = opaque;
    if (!c || !live)
        return -1;
    const struct plasma_swd_ps_admission *a = &c->admission;
    char buf[PLASMA_SWD_PS_JOURNAL_MAX];
    size_t len = 0;
    struct stat st;
    memset(live, 0, sizeof(*live));

    if (c->require_root && geteuid() != 0)
        return -1;
    const int64_t now = c->now ? c->now() : real_now();
    if (now >= a->record_expires_epoch || now >= a->electrical_expires_epoch)
        return -1;

    /* 1. The record itself is unchanged and still root-private. */
    if (read_file(c->record_path, buf, sizeof(buf), &len, true, true, NULL) ||
        len != c->record_len || memcmp(buf, c->record_bytes, len) != 0)
        return -1;

    /* 2. Current boot. */
    if (read_file(c->paths.boot_id, buf, sizeof(buf), &len, false, false, NULL))
        return -1;
    while (len && (buf[len - 1] == '\n' || buf[len - 1] == ' '))
        buf[--len] = '\0';
    if (len != 36)
        return -1;
    memcpy(live->boot_id, buf, 37);

    /* 3. FPGA Manager still operating. */
    if (read_file(c->paths.manager_state, buf, sizeof(buf), &len, false, false, NULL))
        return -1;
    live->manager_operating = strncmp(buf, "operating", 9) == 0 &&
        (buf[9] == '\n' || buf[9] == '\0');

    /* 4. Root journal: same inode/size/mtime as at admission; content still
     * the held IMAGE of this session/boot/manifest/firmware. */
    if (read_file(c->paths.root_journal, buf, sizeof(buf), &len, true, true, &st) ||
        (uint64_t)st.st_dev != a->journal_dev ||
        (uint64_t)st.st_ino != a->journal_ino ||
        (uint64_t)st.st_size != a->journal_size ||
        mtime_ns(&st) != a->journal_mtime_ns)
        return -1;
    live->active_image_attested =
        contains_kv(buf, "status", "IMAGE") &&
        contains_kv(buf, "boot_id", live->boot_id) &&
        contains_kv(buf, "session_id", a->identity.root_image_session_id) &&
        contains_kv(buf, "manifest_sha256", a->identity.image_manifest_sha256) &&
        contains_kv(buf, "firmware_sha256", a->firmware_sha256) &&
        contains_kv(buf, "image_id", a->identity.image_id);
    if (!live->active_image_attested)
        return -1;
    memcpy(live->root_image_session_id, a->identity.root_image_session_id,
           sizeof(live->root_image_session_id));
    memcpy(live->image_manifest_sha256, a->identity.image_manifest_sha256,
           sizeof(live->image_manifest_sha256));
    memcpy(live->loaded_image_sha256, a->firmware_sha256,
           sizeof(live->loaded_image_sha256));
    memcpy(live->image_id, a->identity.image_id, sizeof(live->image_id));

    /* 5. Protected Root source pin unchanged. */
    if (read_file(c->paths.root_pin, buf, sizeof(buf), &len, false, true, NULL) ||
        len != 41 || buf[40] != '\n')
        return -1;
    buf[40] = '\0';
    memcpy(live->root_source_commit, buf, 41);
    live->root_source_pinned =
        strcmp(live->root_source_commit, a->identity.root_source_commit) == 0;

    /* 6. Owner on-site electrical attestation: same root-private file,
     * not expired. This is an attestation, NOT a voltage measurement. */
    if (read_file(a->electrical_path, buf, sizeof(buf), &len, true, true, &st) ||
        (uint64_t)st.st_ino != a->electrical_ino ||
        mtime_ns(&st) != a->electrical_mtime_ns)
        return -1;
    live->voltage_qualified = a->identity.voltage_qualified;

    /* Facts proven by the Root admission at issue time; they stay valid
     * because the reload fence is held and the journal is unchanged. */
    live->abi_version = a->identity.abi_version;
    live->site_bitmap = a->identity.site_bitmap;
    live->axi_isolation_proven = a->identity.axi_isolation_proven;
    live->owner_scan_complete = a->identity.owner_scan_complete;
    live->recovery_available = a->identity.recovery_available;
    return 0;
}

void plasma_swd_ps_default_paths(struct plasma_swd_ps_paths *p)
{
    memset(p, 0, sizeof(*p));
    strcpy(p->boot_id, "/proc/sys/kernel/random/boot_id");
    strcpy(p->manager_state, "/sys/class/fpga_manager/fpga0/state");
    strcpy(p->root_journal,
           "/root/plasma-path2-approved/.plasma-fpga-image-deployment-state.json");
    strcpy(p->root_pin, "/root/plasma-path2-approved/.plasma-path2-source-commit");
    strcpy(p->record_dir, "/run/plasma-z2-swd05");
    strcpy(p->lock, PLASMA_SWD_MMIO_OWNER_LOCK);
    strcpy(p->devmem, "/dev/mem");
}

int plasma_swd_ps_load_admission(struct plasma_swd_ps_live_ctx *c,
                                 unsigned int site_id)
{
    if (!c || (site_id != 1u && site_id != 2u))
        return PLASMA_SWD_BAD_ARG;
    int n = snprintf(c->record_path, sizeof(c->record_path),
                     "%s/swd-site%u-admission", c->paths.record_dir, site_id);
    if (n < 1 || (size_t)n >= sizeof(c->record_path))
        return PLASMA_SWD_BAD_ARG;
    if (read_file(c->record_path, c->record_bytes, sizeof(c->record_bytes),
                  &c->record_len, true, true, NULL))
        return PLASMA_SWD_NOT_READY;
    if (plasma_swd_ps_admission_parse(c->record_bytes, c->record_len,
                                      &c->admission) != PLASMA_SWD_OK ||
        c->admission.site_id != site_id)
        return PLASMA_SWD_NOT_READY;
    return PLASMA_SWD_OK;
}

/* ------------------------------------------------------------------ */
/* Process lifecycle                                                   */
/* ------------------------------------------------------------------ */

static struct {
    unsigned int site;
    bool attached;
    int fd;
    struct plasma_swd_ps_live_ctx live;
    struct plasma_swd_owner_lock lock;
    struct plasma_swd_owner_evidence evidence;
    struct plasma_swd_ps_mapping mapping;
    struct plasma_swd_lease_word_port lease;
    struct plasma_swd_fifo fifo;
    bool paths_overridden;
    struct plasma_swd_ps_paths override;
} g = {.fd = -1};

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
    if (g.evidence.configured)
        plasma_swd_owner_evidence_revoke_all(&g.evidence);
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
    memset(&g.live, 0, sizeof(g.live));
    memset(&g.evidence, 0, sizeof(g.evidence));
    memset(&g.mapping, 0, sizeof(g.mapping));
    memset(&g.lease, 0, sizeof(g.lease));
    memset(&g.fifo, 0, sizeof(g.fifo));
    struct plasma_swd_owner_lock fresh = {.fd = -1, .site_fd = -1};
    fresh.epoch = g.lock.epoch;
    g.lock = fresh;
    if (g.paths_overridden)
        g.live.paths = g.override;
    else
        plasma_swd_ps_default_paths(&g.live.paths);
#ifdef PLASMA_SWD_HOST_TEST
    g.live.require_root = false;
#else
    g.live.require_root = true;
    if (geteuid() != 0) {
        set_err(err, err_len, "PS_OWNER_ROOT_REQUIRED");
        return PLASMA_SWD_NOT_READY;
    }
#endif
    /* Lock FIRST: from here the Root Loader cannot take the reload fence. */
    if (plasma_swd_owner_lock_acquire_site(&g.lock, g.live.paths.lock, g.site)) {
        set_err(err, err_len, "PS_OWNER_SITE_LOCK_UNAVAILABLE");
        return PLASMA_SWD_NOT_READY;
    }
    if (plasma_swd_ps_load_admission(&g.live, g.site) != PLASMA_SWD_OK) {
        set_err(err, err_len, "PS_OWNER_ADMISSION_RECORD_INVALID");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    struct plasma_swd_observed_identity probe;
    if (plasma_swd_ps_read_live(&g.live, &probe) != 0) {
        set_err(err, err_len, "PS_OWNER_LIVE_FACTS_DENIED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    if (plasma_swd_owner_evidence_init(&g.evidence, g.site, 1u,
                                       &g.live.admission.identity, &g.live,
                                       plasma_swd_ps_read_live) != PLASMA_SWD_OK) {
        set_err(err, err_len, "PS_OWNER_EVIDENCE_INCOMPLETE");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
#ifdef PLASMA_SWD_HOST_TEST
    g.fd = open(g.live.paths.devmem, O_RDWR | O_CLOEXEC);
#else
    g.fd = open(g.live.paths.devmem, O_RDWR | O_SYNC | O_CLOEXEC);
#endif
    if (g.fd < 0) {
        set_err(err, err_len, "PS_OWNER_DEVMEM_OPEN_FAILED");
        release_all();
        return PLASMA_SWD_NOT_READY;
    }
    if (plasma_swd_ps_mapping_attach(&g.mapping, g.fd, &g.lock, g.site, 1u,
                                     &g.evidence,
                                     plasma_swd_owner_evidence_authorize,
                                     plasma_swd_owner_evidence_revoke_all)) {
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
    /* Still under this process's Site lock + live admission. The FIFO may
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

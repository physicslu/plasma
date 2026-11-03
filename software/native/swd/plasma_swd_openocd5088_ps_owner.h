/* SPDX-License-Identifier: GPL-2.0-or-later
 * PS-local OpenOCD 5088db4c owner for ONE ABI-v5 Site (Z2 PS, root).
 *
 * The Root-side admission (scripts/z2/plasma_swd_site_admission.py) runs the
 * protected Root G5 admission, verifies the Root journal/Image/Golden and the
 * owner on-site DUT electrical attestation, and writes a root-only admission
 * record. This module:
 *   - holds the PPU reload fence (LOCK_SH) + per-Site lock (LOCK_EX), so the
 *     Root Loader cannot reconfigure PL while OpenOCD owns the Site;
 *   - loads the record as the immutable EXPECTED identity;
 *   - re-measures LIVE facts on EVERY MMIO word (boot ID, FPGA Manager state,
 *     Root journal content/inode, Root source pin, record and electrical
 *     attestation presence/expiry) via plasma_swd_owner_evidence;
 *   - maps exactly one 4-KiB Site page from /dev/mem (O_RDWR|O_SYNC).
 * It never loads FPGA, never writes the journal and never fabricates facts.
 * DUT voltage is NOT measured by hardware: the only source is the owner's
 * on-site attestation, recorded as such.
 */
#ifndef PLASMA_SWD_OPENOCD5088_PS_OWNER_H
#define PLASMA_SWD_OPENOCD5088_PS_OWNER_H

#include "plasma_swd_owner_evidence.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

#define PLASMA_SWD_PS_RECORD_MAX 4096u
#define PLASMA_SWD_PS_JOURNAL_MAX 4096u

struct plasma_swd_ps_paths {
    char boot_id[256];
    char manager_state[256];
    char root_journal[256];
    char code_manifest[256];
    char record_dir[256];   /* record: <dir>/swd-site<N>-admission */
    char lock[256];         /* PPU reload fence path */
    char devmem[256];
};

/* Parsed root-only admission record (key=value lines). */
struct plasma_swd_ps_admission {
    struct plasma_swd_observed_identity identity;
    unsigned int site_id;
    char firmware_sha256[65];
    uint64_t journal_dev, journal_ino, journal_size;
    uint64_t code_manifest_dev, code_manifest_ino, code_manifest_size;
    int64_t code_manifest_mtime_ns;
    int64_t journal_mtime_ns;
    uint64_t electrical_ino;
    int64_t electrical_mtime_ns;
    char electrical_path[256];
    int64_t electrical_expires_epoch;
    int64_t record_expires_epoch;
};

/* Pure parser; no I/O. Returns PLASMA_SWD_OK only for a complete record. */
int plasma_swd_ps_admission_parse(const char *text, size_t len,
                                  struct plasma_swd_ps_admission *out);

/* Live re-measurement context consumed by owner_evidence->read_live. */
struct plasma_swd_ps_live_ctx {
    struct plasma_swd_ps_paths paths;
    struct plasma_swd_ps_admission admission;
    char record_path[300];
    char record_bytes[PLASMA_SWD_PS_RECORD_MAX];
    size_t record_len;
    bool require_root;
    int64_t (*now)(void);
};

/* owner_evidence read_live callback (returns 0 only if every live fact holds). */
int plasma_swd_ps_read_live(void *ctx, struct plasma_swd_observed_identity *live);

/* Load the record for site into ctx (root-only file checks included). */
int plasma_swd_ps_load_admission(struct plasma_swd_ps_live_ctx *ctx,
                                 unsigned int site_id);

void plasma_swd_ps_default_paths(struct plasma_swd_ps_paths *paths);

/* Full OpenOCD-process lifecycle (production entry points). */
int plasma_swd_ps_owner_select_site(unsigned int site_id);
unsigned int plasma_swd_ps_owner_selected_site(void);
int plasma_swd_ps_owner_attach(char *err, size_t err_len);
/* Idle-only OFF: CONTROL=0 then MODE=0, only after STATUS/LEVELS prove the
 * engine idle and fault-free; otherwise performs NO MMIO. */
int plasma_swd_ps_owner_safe_off(char *err, size_t err_len);
void plasma_swd_ps_owner_detach(void);

#ifdef PLASMA_SWD_HOST_TEST
void plasma_swd_ps_owner_set_paths_for_host_test(
    const struct plasma_swd_ps_paths *paths);
#endif
#endif

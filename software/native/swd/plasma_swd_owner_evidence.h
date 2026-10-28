/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only design contract for ongoing PS-local Root/PL identity evidence.
 * This IS NOT an authenticator or a new per-Image approval token.
 *
 * A future protected Root-controlled issuer supplies the immutable expected
 * identity from its actually source-pinned current-boot Image/Manifest facts.
 * A separate trusted native owner re-measures LIVE state at every access.
 * Caller-provided synthetic proofs cannot qualify real hardware.
 */
#ifndef PLASMA_SWD_OWNER_EVIDENCE_H
#define PLASMA_SWD_OWNER_EVIDENCE_H

#include "plasma_swd_fifo_core.h"
#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

struct plasma_swd_observed_identity {
    char boot_id[37];                /* exact Linux boot UUID */
    char root_source_sha256[65];     /* protected Root executable pin */
    char image_manifest_sha256[65];  /* paired Manifest content hash */
    char loaded_image_sha256[65];    /* physically attested current PL Image */
    char image_id[32];              /* ABI-v5 FPGA Image identity */
    char root_image_session_id[38];/* existing Root image journal session ID */
    unsigned int abi_version;
    uint32_t site_bitmap;
    bool root_source_pinned;
    bool manager_operating;
    bool active_image_attested;
    bool axi_isolation_proven;
    bool owner_scan_complete;
    bool voltage_qualified;
    bool recovery_available;
};

struct plasma_swd_owner_evidence {
    struct plasma_swd_observed_identity expected;
    void *trusted_ctx;
    /* MUST obtain live values from the trusted Root/PS boundary, not
     * copy expected back. This function is MOCK-ONLY in this PR.
     * Fail when Root source pin, PL Image, voltage or Boot is unknown.
     */
    int (*read_live)(void *, struct plasma_swd_observed_identity *);
    pid_t creator_pid;
    unsigned int site_id;
    uint64_t lease_generation;
    bool blocked;
    bool configured;
};

int plasma_swd_owner_evidence_init(
    struct plasma_swd_owner_evidence *owner, unsigned int site_id,
    uint64_t lease_generation,
    const struct plasma_swd_observed_identity *root_expected,
    void *trusted_ctx,
    int (*read_live)(void *, struct plasma_swd_observed_identity *));

/* Existing Native C Word Port uses this per-access authorize callback. */
int plasma_swd_owner_evidence_authorize(
    void *ctx, unsigned int site_id, uint64_t lease_generation);
/* Shared-domain poison callback; no automatic requalification/replay. */
void plasma_swd_owner_evidence_revoke_all(void *ctx);
#endif

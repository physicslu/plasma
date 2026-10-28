/* SPDX-License-Identifier: GPL-2.0-or-later
 * C identity comparison; no Root credential, device open or FPGA access.
 * A matched injected snapshot is only Host-only contract evidence.
 */
#include "plasma_swd_owner_evidence.h"

#include <string.h>
#include <unistd.h>

static bool hex64(const char value[65])
{
    if (!value || value[64] != '\0')
        return false;
    for (unsigned i = 0; i < 64; ++i) {
        if (!((value[i] >= '0' && value[i] <= '9') ||
              (value[i] >= 'a' && value[i] <= 'f')))
            return false;
    }
    return true;
}

static bool boot_uuid(const char value[37])
{
    if (!value || value[36] != '\0')
        return false;
    for (unsigned i = 0; i < 36; ++i) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (value[i] != '-')
                return false;
        } else if (!((value[i] >= '0' && value[i] <= '9') ||
                     (value[i] >= 'a' && value[i] <= 'f'))) {
            return false;
        }
    }
    return true;
}

static bool image_name(const char value[32])
{
    if (!value || value[0] == '\0' || value[31] != '\0')
        return false;
    bool terminated = false;
    for (unsigned i = 0; i < 31; ++i) {
        const char c = value[i];
        if (c == '\0') {
            terminated = true;
            break;
        }
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-'))
            return false;
    }
    return terminated;
}

static bool session_id(const char value[38])
{
    if (!value || memcmp(value, "fpga-", 5) != 0 || value[37] != '\0')
        return false;
    for (unsigned i = 5; i < 37; ++i) {
        if (!((value[i] >= '0' && value[i] <= '9') ||
              (value[i] >= 'a' && value[i] <= 'f')))
            return false;
    }
    return true;
}

static bool complete(const struct plasma_swd_observed_identity *v,
                     unsigned int site)
{
    return v && (site == 1u || site == 2u) &&
           boot_uuid(v->boot_id) &&
           hex64(v->root_source_sha256) &&
           hex64(v->image_manifest_sha256) &&
           hex64(v->loaded_image_sha256) &&
           image_name(v->image_id) &&
           session_id(v->root_image_session_id) &&
           v->abi_version == 5u &&
           (v->site_bitmap & (1u << (site - 1u))) != 0u &&
           v->root_source_pinned && v->manager_operating &&
           v->active_image_attested && v->axi_isolation_proven &&
           v->owner_scan_complete && v->voltage_qualified &&
           v->recovery_available;
}

static bool same(const struct plasma_swd_observed_identity *a,
                 const struct plasma_swd_observed_identity *b)
{
    return strcmp(a->boot_id, b->boot_id) == 0 &&
           strcmp(a->root_source_sha256, b->root_source_sha256) == 0 &&
           strcmp(a->image_manifest_sha256,
                  b->image_manifest_sha256) == 0 &&
           strcmp(a->loaded_image_sha256, b->loaded_image_sha256) == 0 &&
           strcmp(a->image_id, b->image_id) == 0 &&
           strcmp(a->root_image_session_id, b->root_image_session_id) == 0 &&
           a->abi_version == b->abi_version &&
           a->site_bitmap == b->site_bitmap;
}

int plasma_swd_owner_evidence_init(
    struct plasma_swd_owner_evidence *owner, unsigned int site_id,
    uint64_t generation,
    const struct plasma_swd_observed_identity *root_expected,
    void *trusted_ctx,
    int (*read_live)(void *, struct plasma_swd_observed_identity *))
{
    if (!owner || owner->configured ||
        !root_expected || !read_live || generation == 0u ||
        !complete(root_expected, site_id))
        return PLASMA_SWD_NOT_READY;
    owner->expected = *root_expected;
    owner->trusted_ctx = trusted_ctx;
    owner->read_live = read_live;
    owner->site_id = site_id;
    owner->lease_generation = generation;
    owner->creator_pid = getpid();
    owner->blocked = false;
    owner->configured = true;
    return PLASMA_SWD_OK;
}

int plasma_swd_owner_evidence_authorize(
    void *ctx, unsigned int site_id, uint64_t generation)
{
    struct plasma_swd_owner_evidence *owner = ctx;
    if (!owner || !owner->configured || owner->blocked ||
        owner->creator_pid != getpid() ||
        owner->site_id != site_id ||
        owner->lease_generation != generation)
        return -1;
    struct plasma_swd_observed_identity live = {0};
    if (!owner->read_live ||
        owner->read_live(owner->trusted_ctx, &live) != 0 ||
        !complete(&live, site_id) ||
        !same(&owner->expected, &live)) {
        owner->blocked = true; /* fail terminally across this owner session */
        return -1;
    }
    return 0;
}

void plasma_swd_owner_evidence_revoke_all(void *ctx)
{
    struct plasma_swd_owner_evidence *owner = ctx;
    if (owner)
        owner->blocked = true;
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * HOST-ONLY adversarial tests: both 'Root' and live observer are fakes.
 * Positives establish typed ABI behavior, NOT genuine Z2 attestation.
 */
#define _POSIX_C_SOURCE 200809L
#include "../plasma_swd_owner_evidence.h"
#include "../plasma_swd_native_words.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct fake_observer {
    struct plasma_swd_observed_identity live;
    unsigned calls;
    bool failure;
};
static int live_read(void *ctx, struct plasma_swd_observed_identity *out)
{
    struct fake_observer *f = ctx;
    f->calls++;
    if (f->failure)
        return -1;
    *out = f->live;
    return 0;
}
static void fill(char dst[65], char c)
{
    memset(dst, c, 64u);
    dst[64] = '\0';
}
static void fill40(char dst[41], char c)
{
    memset(dst, c, 40u);
    dst[40] = '\0';
}

static struct plasma_swd_observed_identity identity(void)
{
    struct plasma_swd_observed_identity e = {0};
    strcpy(e.boot_id, "123e4567-e89b-12d3-a456-426614174000");
    strcpy(e.image_id, "SWD_V5");
    fill40(e.root_source_commit, 'a');
    fill(e.image_manifest_sha256, 'b');
    fill(e.loaded_image_sha256, 'c');
    strcpy(e.root_image_session_id, "fpga-0123456789abcdef0123456789abcdef");
    e.abi_version = 5u;
    e.site_bitmap = 3u;
    e.root_source_pinned = true;
    e.manager_operating = true;
    e.active_image_attested = true;
    e.axi_isolation_proven = true;
    e.owner_scan_complete = true;
    e.voltage_qualified = true;
    e.recovery_available = true;
    return e;
}
static void negative_expected_claims(void)
{
    struct plasma_swd_observed_identity e = identity();
    struct fake_observer f = {.live = e};
    struct plasma_swd_owner_evidence ctx = {0};
    /* Current actual protected Root reports UNPROVEN on these two
     * dimensions. Never turn its journal or manifest into a pass.
     */
    e.active_image_attested = false;
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    e = identity();
    e.axi_isolation_proven = false;
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    e = identity();
    e.root_source_pinned = false;
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    e = identity();
    e.manager_operating = false;
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    e = identity();
    e.voltage_qualified = false;
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    e = identity();
    e.image_manifest_sha256[0] = '\0';
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    e = identity();
    strcpy(e.boot_id, "not-a-valid-boot-id");
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    e = identity();
    assert(plasma_swd_owner_evidence_init(
        &ctx, 3, 11, &e, &f, live_read) != PLASMA_SWD_OK);
    assert(plasma_swd_owner_evidence_init(
        &ctx, 1, 0, &e, &f, live_read) != PLASMA_SWD_OK);
    assert(f.calls == 0);
}

static void negative_live_claims(void)
{
    struct plasma_swd_observed_identity e = identity();
    struct fake_observer f = {.live = e};
    struct plasma_swd_owner_evidence owner = {0};
    assert(plasma_swd_owner_evidence_init(
        &owner, 1, 11, &e, &f, live_read) == PLASMA_SWD_OK);
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) == 0);
    assert(f.calls == 1);
    assert(plasma_swd_owner_evidence_authorize(&owner, 2, 11) != 0);
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 22) != 0);
    assert(f.calls == 1); /* wrong Site/gen rejected before observer */

    f.live.root_image_session_id[6] = '9';
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0);
    assert(owner.blocked);
    f.live = e;
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0);

    struct plasma_swd_observed_identity *v = &f.live;
    /* Different sessions: every unknown/live drift causes TERMINAL deny. */
#define BAD_LIVE(field, replacement) do { \
    memset(&owner, 0, sizeof(owner)); \
    f.live = e; \
    assert(plasma_swd_owner_evidence_init( \
        &owner, 1, 11, &e, &f, live_read) == 0); \
    v->field = (replacement); \
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0); \
    assert(owner.blocked); \
} while (0)
    BAD_LIVE(active_image_attested, false);
    BAD_LIVE(axi_isolation_proven, false);
    BAD_LIVE(voltage_qualified, false);
    BAD_LIVE(root_source_pinned, false);
    BAD_LIVE(manager_operating, false);
    BAD_LIVE(recovery_available, false);
    BAD_LIVE(owner_scan_complete, false);
    BAD_LIVE(root_source_pinned, false);
    BAD_LIVE(abi_version, 4u);
    BAD_LIVE(site_bitmap, 2u);
#undef BAD_LIVE
    memset(&owner, 0, sizeof(owner));
    f.live = e;
    assert(plasma_swd_owner_evidence_init(
        &owner, 1, 11, &e, &f, live_read) == 0);
    strcpy(f.live.boot_id, "123e4567-e89b-12d3-a456-426614174001");
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0);
    memset(&owner, 0, sizeof(owner));
    f.live = e;
    assert(plasma_swd_owner_evidence_init(
        &owner, 1, 11, &e, &f, live_read) == 0);
    f.live.image_manifest_sha256[0] = '0';
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0);
    memset(&owner, 0, sizeof(owner));
    f.live = e;
    assert(plasma_swd_owner_evidence_init(
        &owner, 1, 11, &e, &f, live_read) == 0);
    f.live.root_source_commit[0] = '0';
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0);
    memset(&owner, 0, sizeof(owner));
    f.live = e;
    assert(plasma_swd_owner_evidence_init(
        &owner, 1, 11, &e, &f, live_read) == 0);
    f.live.loaded_image_sha256[0] = '0';
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0);
    memset(&owner, 0, sizeof(owner));
    f.live = e;
    assert(plasma_swd_owner_evidence_init(
        &owner, 1, 11, &e, &f, live_read) == 0);
    f.failure = true;
    assert(plasma_swd_owner_evidence_authorize(&owner, 1, 11) != 0);
    assert(owner.blocked);
}

static void fake_mapping_chain(void)
{
    char lock_path[] = "/tmp/plasma-evidence-swd-XXXXXX";
    int fd = mkstemp(lock_path);
    assert(fd >= 0);
    assert(close(fd) == 0);
    struct plasma_swd_owner_lock lock = {.fd = -1, .site_fd = -1};
    assert(plasma_swd_owner_lock_acquire_site(&lock, lock_path, 1u) == 0);
    struct plasma_swd_observed_identity expected = identity();
    struct fake_observer f = {.live = expected};
    struct plasma_swd_owner_evidence owner = {0};
    assert(plasma_swd_owner_evidence_init(
        &owner, 1u, 11u, &expected, &f, live_read) == 0);
    uint32_t page[1024] = {0};
    page[0] = PLASMA_SWD_ABI_V5 | 1u;
    struct plasma_swd_native_words native;
    assert(plasma_swd_native_words_init(
        &native, page, sizeof(page), &lock, 1, 11, &owner,
        plasma_swd_owner_evidence_authorize,
        plasma_swd_owner_evidence_revoke_all) == 0);
    struct plasma_swd_lease_provider provider =
        plasma_swd_native_words_provider(&native);
    struct plasma_swd_lease_word_port lease;
    assert(plasma_swd_lease_word_port_init(
        &lease, &provider, &lock, 1, 11) == 0);
    assert(plasma_swd_lease_word_port_admit(&lease) == 0);
    struct plasma_swd_word_io io;
    assert(plasma_swd_lease_word_port_make_io(&lease, &io) == 0);
    assert(io.write32(io.ctx, PLASMA_SWD_SITE1_BASE + 0x10, 0x55AA) == 0);
    assert(page[4] == 0x55AA);
    unsigned before = f.calls;
    f.live.active_image_attested = false; /* actual Root currently unproven */
    assert(io.write32(io.ctx, PLASMA_SWD_SITE1_BASE + 0x10, 0x1234) != 0);
    assert(page[4] == 0x55AA);
    assert(lease.poisoned && owner.blocked);
    assert(f.calls > before);
    f.live = expected;
    assert(io.write32(io.ctx, PLASMA_SWD_SITE1_BASE + 0x10, 2) != 0);
    plasma_swd_lease_word_port_retire(&lease);
    plasma_swd_native_words_retire(&native);
    plasma_swd_owner_lock_release(&lock);
    char site_path[512];
    assert(snprintf(site_path, sizeof(site_path),
                    "%s.site-1", lock_path) > 0);
    assert(unlink(site_path) == 0);
    assert(unlink(lock_path) == 0);
}

int main(void)
{
    negative_expected_claims();
    negative_live_claims();
    fake_mapping_chain();
    puts("PLASMA_PSNATIVE_LIVE_EVIDENCE_HOST_ONLY_PASS");
    return 0;
}

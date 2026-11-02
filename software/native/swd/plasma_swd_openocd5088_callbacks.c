/* SPDX-License-Identifier: GPL-2.0-or-later
 * Candidate OpenOCD 5088db4c SWD callback binding to the PLASMA FIFO C core.
 * Must be compiled *inside* a source-locked OpenOCD tree: jtag/swd.h.
 * Adapter registration and ABI-v5 C word provider are built in pinned
 * OpenOCD Host-only CI. A trusted physical PS-local Root/Image authority,
 * mapping admission and target hardware qualification are NOT provided.
 */
#include "plasma_swd_fifo_core.h"
#include "plasma_swd_openocd5088_binding.h"

#include <jtag/swd.h>

#include <stddef.h>
#include <stdint.h>

/* One PS-local OpenOCD process may bind one externally leased Site.
 * Concurrent Sites use independent OpenOCD processes; never a shared global
 * scheduler or automatic fallback to old remote-bitbang GPIO.
 */
static struct plasma_swd_fifo *active_site;
static struct plasma_swd_lease_word_port *active_lease;
static struct plasma_swd_native_words *active_native;

/* Verify the complete source-specific provider ABI, not merely a shared
 * void* context that a caller could accidentally pair with wrong callbacks.
 */
static bool native_provider_matches(
    const struct plasma_swd_lease_word_port *lease,
    struct plasma_swd_native_words *native)
{
    if (!lease || !native)
        return false;
    const struct plasma_swd_lease_provider expected =
        plasma_swd_native_words_provider(native);
    return lease->provider.ctx == expected.ctx &&
           lease->provider.qualify == expected.qualify &&
           lease->provider.read_owned == expected.read_owned &&
           lease->provider.write_owned == expected.write_owned &&
           lease->provider.barrier_owned == expected.barrier_owned &&
           lease->provider.invalidate_all == expected.invalidate_all;
}

/* Never accept a naked 'admitted' FIFO: that flag is insufficient proof
 * of a live owner. Assert the entire exact native-word/lease/IO chain.
 */
int plasma_swd_openocd5088_bind_guarded(
    struct plasma_swd_fifo *site,
    struct plasma_swd_lease_word_port *lease,
    struct plasma_swd_native_words *native)
{
    struct plasma_swd_word_io io = {0};
    if (!site || !lease || !native || active_site ||
        !site->admitted || site->blocked ||
        !lease->admitted || lease->poisoned ||
        native->poisoned || !native->words ||
        !plasma_swd_owner_lock_valid(lease->process_lock) ||
        lease->process_lock->site_id != lease->site_id ||
        lease->process_lock != native->owner ||
        lease->site_id != native->site ||
        lease->generation != native->lease_generation ||
        lease->base != native->base || site->base != lease->base ||
        lease->owner_lock_epoch != native->owner_epoch ||
        !native_provider_matches(lease, native) ||
        plasma_swd_native_words_ready(native) != PLASMA_SWD_OK ||
        plasma_swd_lease_word_port_make_io(lease, &io) != PLASMA_SWD_OK ||
        site->io.ctx != io.ctx || site->io.read32 != io.read32 ||
        site->io.write32 != io.write32 ||
        site->io.write_barrier != io.write_barrier)
        return ERROR_FAIL;

    /* A callback that merely returns success is NOT a Root attestation.
     * This is a wiring/safety boundary, not a source of device authority.
     */
    active_site = site;
    active_lease = lease;
    active_native = native;
    return ERROR_OK;
}

void plasma_swd_openocd5088_unbind(void)
{
    if (active_site) {
        active_site->admitted = false;
        active_site->blocked = true;
        active_site->count = 0; /* no replay after cleanup */
    }
    active_site = NULL;
    active_lease = NULL;
    active_native = NULL;
}

static int core_result(int code)
{
    switch (code) {
    case PLASMA_SWD_OK: return ERROR_OK;
    case PLASMA_SWD_ACK_WAIT: return ERROR_WAIT;
    case PLASMA_SWD_ACK_FAULT: return ERROR_SWD_FAULT;
    case PLASMA_SWD_BAD_RESPONSE:
    case PLASMA_SWD_IO_UNCERTAIN: return ERROR_SWD_FAIL;
    default: return ERROR_FAIL;
    }
}

/* OpenOCD swd_select() invokes swd_ops.init() *before*
 * adapter_driver.init(). This callback is pure transport declaration and
 * MUST NOT touch a PS device or require a Site lease. Real admission is
 * enforced by adapter_driver.init() and every later I/O callback.
 */
static int plasma_transport_select(void)
{
    return ERROR_OK;
}

int plasma_swd_openocd5088_owner_ready(void)
{
    struct plasma_swd_word_io io = {0};
    if (active_site && active_lease && active_native &&
        active_site->admitted && !active_site->blocked &&
        active_lease->admitted && !active_lease->poisoned &&
        active_native->owner == active_lease->process_lock &&
        native_provider_matches(active_lease, active_native) &&
        active_native->site == active_lease->site_id &&
        active_native->lease_generation == active_lease->generation &&
        plasma_swd_native_words_ready(active_native) == PLASMA_SWD_OK &&
        plasma_swd_lease_word_port_make_io(active_lease, &io) == PLASMA_SWD_OK &&
        active_site->io.ctx == io.ctx &&
        active_site->io.read32 == io.read32 &&
        active_site->io.write32 == io.write32 &&
        active_site->io.write_barrier == io.write_barrier)
        return ERROR_OK;
    if (active_site) {
        /* Fail closed on any observed owner loss: pending writes are
         * discarded, not delayed/replayed into a different FPGA Image.
         */
        active_site->admitted = false;
        active_site->blocked = true;
        active_site->count = 0;
    }
    return ERROR_FAIL;
}

static int plasma_read(uint8_t cmd, uint32_t *value, uint32_t ap_delay_hint)
{
    if (plasma_swd_openocd5088_owner_ready() != ERROR_OK)
        return ERROR_FAIL;
    return core_result(plasma_swd_fifo_queue_read(
        active_site, cmd, value, ap_delay_hint));
}

static int plasma_write(uint8_t cmd, uint32_t value, uint32_t ap_delay_hint)
{
    if (plasma_swd_openocd5088_owner_ready() != ERROR_OK)
        return ERROR_FAIL;
    return core_result(plasma_swd_fifo_queue_write(
        active_site, cmd, value, ap_delay_hint));
}

static int plasma_swj(enum swd_special_seq seq)
{
    const uint8_t *bits = NULL;
    unsigned int count = 0;
    if (plasma_swd_openocd5088_owner_ready() != ERROR_OK)
        return ERROR_FAIL;
    switch (seq) {
    case LINE_RESET: bits = swd_seq_line_reset;
        count = swd_seq_line_reset_len; break;
    case JTAG_TO_SWD: bits = swd_seq_jtag_to_swd;
        count = swd_seq_jtag_to_swd_len; break;
    case SWD_TO_JTAG: bits = swd_seq_swd_to_jtag;
        count = swd_seq_swd_to_jtag_len; break;
    case SWD_TO_DORMANT: bits = swd_seq_swd_to_dormant;
        count = swd_seq_swd_to_dormant_len; break;
    case DORMANT_TO_SWD: bits = swd_seq_dormant_to_swd;
        count = swd_seq_dormant_to_swd_len; break;
    case JTAG_TO_DORMANT: bits = swd_seq_jtag_to_dormant;
        count = swd_seq_jtag_to_dormant_len; break;
    case DORMANT_TO_JTAG: bits = swd_seq_dormant_to_jtag;
        count = swd_seq_dormant_to_jtag_len; break;
    default: return ERROR_FAIL;
    }
    if (count > 256u)
        return ERROR_FAIL;
    return core_result(plasma_swd_fifo_queue_swj(active_site, bits,
                                                  (uint16_t)count));
}

static int plasma_run(void)
{
    if (plasma_swd_openocd5088_owner_ready() != ERROR_OK)
        return ERROR_FAIL;
    return core_result(plasma_swd_fifo_run(active_site));
}

/* Source-locked OpenOCD 5088db4c struct swd_driver callback signatures.
 * Adapter init/quit/CLI are linked in the exact source-locked build.
 * No live hardware owner or MMIO mapping is installed automatically.
 */
const struct swd_driver plasma_swd_openocd5088_ops = {
    .init = plasma_transport_select,
    .switch_seq = plasma_swj,
    .read_reg = plasma_read,
    .write_reg = plasma_write,
    .run = plasma_run,
};

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Candidate OpenOCD 5088db4c SWD callback binding to the PLASMA FIFO C core.
 * Must be compiled *inside* a source-locked OpenOCD tree: jtag/swd.h.
 * NO adapter_driver registration, Linux MMIO provider, FPGA Image admission,
 * executable build, or target hardware qualification is provided here.
 */
#include "plasma_swd_fifo_core.h"

#include <jtag/swd.h>

#include <stddef.h>
#include <stdint.h>

/* One PS-local OpenOCD process may bind one externally leased Site.
 * Concurrent Sites use independent OpenOCD processes; never a shared global
 * scheduler or automatic fallback to old remote-bitbang GPIO.
 */
static struct plasma_swd_fifo *active_site;

int plasma_swd_openocd5088_bind(struct plasma_swd_fifo *site)
{
    if (!site || !site->admitted || site->blocked || active_site)
        return ERROR_FAIL;
    active_site = site;
    return ERROR_OK;
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

static int plasma_init(void)
{
    return active_site && active_site->admitted && !active_site->blocked
        ? ERROR_OK : ERROR_FAIL;
}

static int plasma_read(uint8_t cmd, uint32_t *value, uint32_t ap_delay_hint)
{
    if (plasma_init() != ERROR_OK)
        return ERROR_FAIL;
    return core_result(plasma_swd_fifo_queue_read(
        active_site, cmd, value, ap_delay_hint));
}

static int plasma_write(uint8_t cmd, uint32_t value, uint32_t ap_delay_hint)
{
    if (plasma_init() != ERROR_OK)
        return ERROR_FAIL;
    return core_result(plasma_swd_fifo_queue_write(
        active_site, cmd, value, ap_delay_hint));
}

static int plasma_swj(enum swd_special_seq seq)
{
    const uint8_t *bits = NULL;
    unsigned int count = 0;
    if (plasma_init() != ERROR_OK)
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
    if (plasma_init() != ERROR_OK)
        return ERROR_FAIL;
    return core_result(plasma_swd_fifo_run(active_site));
}

/* Source-locked OpenOCD 5088db4c struct swd_driver callback signatures.
 * Still requires reviewed OpenOCD adapter_driver init/quit/transport CLI
 * registration and explicit approved Linux owner/IO binding before use.
 */
const struct swd_driver plasma_swd_openocd5088_ops = {
    .init = plasma_init,
    .switch_seq = plasma_swj,
    .read_reg = plasma_read,
    .write_reg = plasma_write,
    .run = plasma_run,
};

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Source-locked OpenOCD 5088db4c: explicit SAME-PROCESS v5 SWD binding.
 * This is not a Root/FPGA Image admission implementation. The trusted
 * caller must establish/own its actual Z2 mapping and authorized C owner
 * before calling this API. No device open, sockets, or hidden fallback.
 */
#ifndef PLASMA_SWD_OPENOCD5088_BINDING_H
#define PLASMA_SWD_OPENOCD5088_BINDING_H
#include "plasma_swd_native_words.h"

struct plasma_swd_fifo;

/* Rejects any FIFO not created from the exact Native C / Lease provider
 * and one unique per-Site owner lock. Caller keeps all pointers alive
 * through adapter quit/unbind.
 */
int plasma_swd_openocd5088_bind_guarded(
    struct plasma_swd_fifo *site,
    struct plasma_swd_lease_word_port *lease,
    struct plasma_swd_native_words *native);

/* Clears queued operations without trying an uncertain MMIO cleanup. */
void plasma_swd_openocd5088_unbind(void);
int plasma_swd_openocd5088_owner_ready(void);
#endif

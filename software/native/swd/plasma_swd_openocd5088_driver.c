/* SPDX-License-Identifier: GPL-2.0-or-later
 * Source-locked OpenOCD 5088db4c adapter registry.
 *
 * Adapter discovery is NOT I/O authority. No PS Site lease or FPGA Image
 * admission is implemented by this standalone C source. Therefore OpenOCD
 * init MUST fail closed until an independently qualified, explicitly
 * owner-authorized PS-local integration binds one admitted Site.
 */
#include <jtag/interface.h>
#include <jtag/swd.h>

extern const struct swd_driver plasma_swd_openocd5088_ops;

static int plasma_swd_adapter_init(void)
{
    return plasma_swd_openocd5088_ops.init();
}

static int plasma_swd_adapter_quit(void)
{
    return ERROR_OK;
}

/* SWCLK is hardware generated within one independent Site NORMAL Engine.
 * No SWD GPIO/remote_bitbang fallback, no JTAG executor.
 */
struct adapter_driver plasma_swd_adapter_driver = {
    .name = "plasma_swd",
    .transport_ids = TRANSPORT_SWD,
    .transport_preferred_id = TRANSPORT_SWD,
    .init = plasma_swd_adapter_init,
    .quit = plasma_swd_adapter_quit,
    .swd_ops = &plasma_swd_openocd5088_ops,
};

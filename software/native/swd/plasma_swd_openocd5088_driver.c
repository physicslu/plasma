/* SPDX-License-Identifier: GPL-2.0-or-later
 * Source-locked OpenOCD 5088db4c adapter registry.
 *
 * Adapter discovery is NOT I/O authority. In the real OpenOCD build,
 * adapter init binds exactly ONE Site through the PS-local owner
 * (plasma_swd_openocd5088_ps_owner.c), which requires a root-only Root
 * admission record, the reload fence + Site lock, live Root journal/boot/
 * Manager/source-pin facts and an unexpired owner electrical attestation.
 * Any missing fact fails closed before MMIO. The Host-only shim build has no
 * PS owner and therefore still fails closed at init.
 */
#ifndef PLASMA_SWD_HOST_TEST
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif
#include <helper/log.h>
#include "plasma_swd_openocd5088_ps_owner.h"
#endif
#include <jtag/interface.h>
#include <jtag/swd.h>
#include "plasma_swd_openocd5088_binding.h"

extern const struct swd_driver plasma_swd_openocd5088_ops;
extern int plasma_swd_openocd5088_owner_ready(void);
#ifndef PLASMA_SWD_HOST_TEST
extern const struct command_registration plasma_swd_command_handlers[];
#endif

/* This is OpenOCD's adapter_driver init, distinct from the earlier
 * swd_driver.init transport-selection callback. Hardware I/O admission
 * occurs ONLY here.
 */
static int plasma_swd_adapter_init(void)
{
#ifndef PLASMA_SWD_HOST_TEST
    char why[96];
    if (plasma_swd_ps_owner_attach(why, sizeof(why)) != PLASMA_SWD_OK) {
        LOG_ERROR("plasma_swd: %s", why);
        return ERROR_FAIL;
    }
    LOG_INFO("plasma_swd: %s site %u", why,
             plasma_swd_ps_owner_selected_site());
#endif
    return plasma_swd_openocd5088_owner_ready();
}

static int plasma_swd_adapter_quit(void)
{
#ifndef PLASMA_SWD_HOST_TEST
    char why[96];
    if (plasma_swd_ps_owner_safe_off(why, sizeof(why)) == PLASMA_SWD_OK)
        LOG_INFO("plasma_swd: %s", why);
    else
        LOG_WARNING("plasma_swd: %s", why);
#endif
    plasma_swd_openocd5088_unbind();
#ifndef PLASMA_SWD_HOST_TEST
    plasma_swd_ps_owner_detach();
#endif
    return ERROR_OK;
}

/* SWCLK is hardware generated within one independent Site NORMAL Engine.
 * No SWD GPIO/remote_bitbang fallback, no JTAG executor.
 */
struct adapter_driver plasma_swd_adapter_driver = {
    .name = "plasma_swd",
    .transport_ids = TRANSPORT_SWD,
    .transport_preferred_id = TRANSPORT_SWD,
#ifndef PLASMA_SWD_HOST_TEST
    .commands = plasma_swd_command_handlers,
#endif
    .init = plasma_swd_adapter_init,
    .quit = plasma_swd_adapter_quit,
    .swd_ops = &plasma_swd_openocd5088_ops,
};

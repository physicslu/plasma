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

/* OpenOCD speed is the RTL HALF_PERIOD: SWCLK = 100 MHz / (2 * HALF).
 * Rounded so the real clock never exceeds the request; no RCLK. */
static int plasma_swd_khz(int khz, int *speed)
{
    if (khz <= 0)
        return ERROR_FAIL;
    unsigned int half = (50000u + (unsigned int)khz - 1u) / (unsigned int)khz;
    if (half < PLASMA_SWD_HALF_MIN)
        half = PLASMA_SWD_HALF_MIN;
    if (half > PLASMA_SWD_HALF_MAX)
        half = PLASMA_SWD_HALF_MAX;
    *speed = (int)half;
    return ERROR_OK;
}

static int plasma_swd_speed_div(int speed, int *khz)
{
    if (speed < (int)PLASMA_SWD_HALF_MIN)
        return ERROR_FAIL;
    *khz = 50000 / speed;
    return ERROR_OK;
}

static int plasma_swd_speed(int speed)
{
#ifndef PLASMA_SWD_HOST_TEST
    if (plasma_swd_ps_owner_set_half_period((uint32_t)speed) != PLASMA_SWD_OK) {
        LOG_ERROR("plasma_swd: cannot set SWCLK half period %d", speed);
        return ERROR_FAIL;
    }
#else
    (void)speed;
#endif
    return ERROR_OK;
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

/* SWCLK is hardware generated within one independent Site NORMAL Engine
 * (adapter speed -> HALF_PERIOD; default 500 kHz, see plasma_swd site).
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
    .speed = plasma_swd_speed,
    .khz = plasma_swd_khz,
    .speed_div = plasma_swd_speed_div,
    .swd_ops = &plasma_swd_openocd5088_ops,
};

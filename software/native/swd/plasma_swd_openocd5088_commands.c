/* SPDX-License-Identifier: GPL-2.0-or-later
 * OpenOCD 5088db4c configuration command for the plasma_swd adapter.
 * Real OpenOCD build only (not the Host-only shim). Selecting a Site grants
 * nothing: adapter init still requires the PS owner Root admission.
 */
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif
#include <helper/command.h>
#include <jtag/interface.h>
#include "plasma_swd_openocd5088_ps_owner.h"

COMMAND_HANDLER(plasma_swd_handle_site_command)
{
    unsigned int site;
    if (CMD_ARGC != 1)
        return ERROR_COMMAND_SYNTAX_ERROR;
    COMMAND_PARSE_NUMBER(uint, CMD_ARGV[0], site);
    if (plasma_swd_ps_owner_select_site(site) != PLASMA_SWD_OK)
        return ERROR_COMMAND_ARGUMENT_INVALID;
    return ERROR_OK;
}

static const struct command_registration plasma_swd_subcommand_handlers[] = {
    {
        .name = "site",
        .handler = plasma_swd_handle_site_command,
        .mode = COMMAND_CONFIG,
        .help = "Select the ONE ABI-v5 Site (1 or 2) this process may own.",
        .usage = "1|2",
    },
    COMMAND_REGISTRATION_DONE
};

const struct command_registration plasma_swd_command_handlers[] = {
    {
        .name = "plasma_swd",
        .mode = COMMAND_ANY,
        .help = "PLASMA ABI-v5 independent SWD Site adapter",
        .chain = plasma_swd_subcommand_handlers,
        .usage = "",
    },
    COMMAND_REGISTRATION_DONE
};

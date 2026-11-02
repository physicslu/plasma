/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only test shape; MUST NOT be confused with genuine OpenOCD headers.
 * Real pinned source is built independently via the hosted source-lock job.
 */
#ifndef PLASMA_SHIM_JTAG_INTERFACE_H
#define PLASMA_SHIM_JTAG_INTERFACE_H
#include <jtag/swd.h>
#define TRANSPORT_SWD (1u << 1)
struct adapter_driver {
    const char *name;
    unsigned int transport_ids;
    unsigned int transport_preferred_id;
    int (*init)(void);
    int (*quit)(void);
    const struct swd_driver *swd_ops;
};
#endif

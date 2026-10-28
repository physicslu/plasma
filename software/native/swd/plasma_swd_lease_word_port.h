/* SPDX-License-Identifier: GPL-2.0-or-later
 * ABI-v5 native C lease boundary to an external, already-qualified
 * SiteMMIO owner. NO device opens, driver privileges or GPIO fallback.
 */
#ifndef PLASMA_SWD_LEASE_WORD_PORT_H
#define PLASMA_SWD_LEASE_WORD_PORT_H
#include "plasma_swd_fifo_core.h"
#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

/* The provider is part of the SAME trusted process. Each owned read/write/
 * barrier callback MUST validate the site, generation and ongoing Image/
 * board-voltage/FPGA owner admission atomically with the operation under
 * the central owner lock. Check-only callbacks cannot protect against
 * asynchronous PL reload or lease revocation. The provider MUST coordinate
 * with Python LinuxMMIO via the SAME /run/lock/plasma-mmio.lock if used.
 * No provider implementation for real hardware is provided in this PR.
 */
struct plasma_swd_lease_provider {
    void *ctx;
    int (*qualify)(void *ctx, unsigned int site, uint32_t base, uint64_t generation);
    int (*read_owned)(void *ctx, unsigned int site, uint32_t base,
                      uint64_t generation, uint32_t address, uint32_t *value);
    int (*write_owned)(void *ctx, unsigned int site, uint32_t base,
                       uint64_t generation, uint32_t address, uint32_t value);
    int (*barrier_owned)(void *ctx, unsigned int site, uint32_t base,
                         uint64_t generation);
    void (*invalidate_all)(void *ctx);
};
struct plasma_swd_lease_word_port {
    struct plasma_swd_lease_provider provider;
    unsigned int site_id;
    uint32_t base;
    uint64_t generation;
    pid_t creator_pid;
    bool admitted;
    bool poisoned;
};
/* Inert construction: validates shape only, does not qualify or touch MMIO. */
int plasma_swd_lease_word_port_init(struct plasma_swd_lease_word_port *port,
                                   const struct plasma_swd_lease_provider *owner,
                                   unsigned int site, uint64_t generation);
/* Single explicit qualification; provider has final authority. */
int plasma_swd_lease_word_port_admit(struct plasma_swd_lease_word_port *port);
int plasma_swd_lease_word_port_make_io(struct plasma_swd_lease_word_port *port,
                                       struct plasma_swd_word_io *io);
void plasma_swd_lease_word_port_retire(struct plasma_swd_lease_word_port *port);
#endif

/* SPDX-License-Identifier: GPL-2.0-or-later
 * PS-local advisory MMIO owner lock, shared with Python LinuxMMIO.
 * A lock is a prerequisite, never device/Image/voltage authorization.
 */
#ifndef PLASMA_SWD_OWNER_LOCK_H
#define PLASMA_SWD_OWNER_LOCK_H

#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

#define PLASMA_SWD_MMIO_OWNER_LOCK "/run/lock/plasma-mmio.lock"

struct plasma_swd_owner_lock {
    int fd;
    pid_t owner_pid;
    uint64_t epoch; /* changes after every successful acquire */
    bool acquired;
};

/* Explicit path for Host-only temporary lock tests. Real integration MUST
 * use PLASMA_SWD_MMIO_OWNER_LOCK, identical to Python LinuxMMIO.
 * Never opens a device or claims an FPGA Site. */
int plasma_swd_owner_lock_acquire(struct plasma_swd_owner_lock *owner,
                                  const char *absolute_path);
bool plasma_swd_owner_lock_valid(const struct plasma_swd_owner_lock *owner);
void plasma_swd_owner_lock_release(struct plasma_swd_owner_lock *owner);
#endif

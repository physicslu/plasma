/* SPDX-License-Identifier: GPL-2.0-or-later
 * PS-local OpenOCD 5088db4c owner for ONE ABI-v5 Site (Z2 PS, root).
 *
 * The adapter only does what the hardware needs:
 *   - holds the PPU reload fence (LOCK_SH) + per-Site lock (LOCK_EX), so the
 *     Root Loader cannot reconfigure PL and no second OpenOCD can drive the
 *     Site while this process owns it;
 *   - once before the first MMIO, requires FPGA Manager "operating" and a
 *     root-private Root journal reporting a loaded Image in this boot (an
 *     access to an absent AXI slave may hang the bus);
 *   - maps exactly one 4-KiB Site page from /dev/mem (O_RDWR|O_SYNC), checks
 *     the Site ID register, recovers a stale Site to OFF, enables it, and
 *     returns it to OFF on quit.
 * Which Image, who may program and the DUT electrical conditions are the
 * caller's policy; the adapter performs no per-word file re-validation.
 */
#ifndef PLASMA_SWD_OPENOCD5088_PS_OWNER_H
#define PLASMA_SWD_OPENOCD5088_PS_OWNER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PLASMA_SWD_PS_JOURNAL_MAX 4096u

struct plasma_swd_ps_paths {
    char boot_id[256];
    char manager_state[256];
    char root_journal[256];
    char lock[256];         /* PPU reload fence path */
    char devmem[256];
};

void plasma_swd_ps_default_paths(struct plasma_swd_ps_paths *paths);

/* Full OpenOCD-process lifecycle (production entry points). */
int plasma_swd_ps_owner_select_site(unsigned int site_id);
unsigned int plasma_swd_ps_owner_selected_site(void);
int plasma_swd_ps_owner_attach(char *err, size_t err_len);
/* Idle-only OFF: CONTROL=0 then MODE=0, only after STATUS/LEVELS prove the
 * engine idle and fault-free; otherwise performs NO MMIO. */
int plasma_swd_ps_owner_safe_off(char *err, size_t err_len);
void plasma_swd_ps_owner_detach(void);

#ifdef PLASMA_SWD_HOST_TEST
void plasma_swd_ps_owner_set_paths_for_host_test(
    const struct plasma_swd_ps_paths *paths);
#endif
#endif

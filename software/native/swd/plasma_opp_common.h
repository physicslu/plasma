/* OPP Common ABI v1: caller-owned MMIO word callbacks, no OpenOCD dependency.
 * Does not open /dev/mem, select a physical base or authorize hardware access.
 */
#ifndef PLASMA_OPP_COMMON_H
#define PLASMA_OPP_COMMON_H

#include <stdint.h>

#define OPP_COMMON_MAGIC UINT32_C(0x4D534C50)
#define OPP_COMMON_ABI UINT32_C(0x00010000)
#define OPP_COMMON_SCRATCH UINT32_C(0x40)

typedef struct {
    void *context;
    int (*read32)(void *context, uint32_t offset, uint32_t *value);
    int (*write32)(void *context, uint32_t offset, uint32_t value);
    int (*barrier)(void *context);
} opp_common_io;

typedef struct {
    uint32_t image_id[4];
    uint32_t build_id[4];
    uint32_t capabilities[2];
    uint32_t site_present;
    uint32_t site_ready;
    uint32_t ppu_status;
    uint32_t hw_revision;
} opp_common_info;

/* Returns 0 on success, negative on failure. No retries on uncertain writes. */
int opp_common_check(const opp_common_io *io);
int opp_common_get_info(const opp_common_io *io, opp_common_info *info);
/* Caller must hold exclusive scratch ownership for entire operation. */
int opp_common_self_test(const opp_common_io *io);

#endif

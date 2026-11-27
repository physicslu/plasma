#include "plasma_opp_common.h"
#include <stddef.h>
#include <string.h>

static int read_word(const opp_common_io *io, uint32_t off, uint32_t *value)
{
    if (!io || !io->read32 || !value)
        return -1;
    return io->read32(io->context, off, value) == 0 ? 0 : -1;
}

static int write_scratch(const opp_common_io *io, uint32_t value)
{
    if (!io || !io->write32 || !io->barrier)
        return -1;
    if (io->write32(io->context, OPP_COMMON_SCRATCH, value) != 0)
        return -1;
    return io->barrier(io->context) == 0 ? 0 : -1;
}

int opp_common_check(const opp_common_io *io)
{
    uint32_t magic, abi;
    if (read_word(io, 0x00, &magic) || read_word(io, 0x04, &abi))
        return -1;
    return (magic == OPP_COMMON_MAGIC && abi == OPP_COMMON_ABI) ? 0 : -2;
}

int opp_common_get_info(const opp_common_io *io, opp_common_info *info)
{
    unsigned i;
    opp_common_info temp;
    if (!info || opp_common_check(io))
        return -1;
    memset(&temp, 0, sizeof(temp));
    for (i = 0; i < 4; ++i) {
        if (read_word(io, 0x08 + i * 4, &temp.image_id[i]) ||
            read_word(io, 0x18 + i * 4, &temp.build_id[i]))
            return -1;
    }
    for (i = 0; i < 2; ++i)
        if (read_word(io, 0x28 + i * 4, &temp.capabilities[i]))
            return -1;
    if (read_word(io, 0x30, &temp.site_present) ||
        read_word(io, 0x34, &temp.site_ready) ||
        read_word(io, 0x38, &temp.ppu_status) ||
        read_word(io, 0x3c, &temp.hw_revision))
        return -1;
    if ((temp.site_present | temp.site_ready) & ~UINT32_C(0xf))
        return -2;
    if (temp.site_ready & ~temp.site_present)
        return -2;
    *info = temp;
    return 0;
}

int opp_common_self_test(const opp_common_io *io)
{
    static const uint32_t patterns[] = {
        UINT32_C(0), UINT32_C(0xffffffff), UINT32_C(0xaaaaaaaa),
        UINT32_C(0x55555555), UINT32_C(0x12345678)
    };
    uint32_t saved, actual;
    unsigned i;
    int failed = 0;
    if (!io || !io->write32 || !io->barrier || opp_common_check(io) ||
        read_word(io, OPP_COMMON_SCRATCH, &saved))
        return -1;
    for (i = 0; i < sizeof(patterns) / sizeof(patterns[0]); ++i) {
        if (write_scratch(io, patterns[i]) ||
            read_word(io, OPP_COMMON_SCRATCH, &actual) ||
            actual != patterns[i]) {
            failed = 1;
            break;
        }
    }
    /* Restore is mandatory even after a failed pattern comparison. */
    if (write_scratch(io, saved) ||
        read_word(io, OPP_COMMON_SCRATCH, &actual) || actual != saved)
        return -3;
    return failed ? -2 : 0;
}

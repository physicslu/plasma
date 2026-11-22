/* Host-only C contract tests: synthetic registers, no MMIO device. */
#include "../plasma_opp_common.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint32_t regs[17];
static int corrupt_scratch;
static int scratch_reads;
static int reads, writes, barriers;

static int fake_read(void *ctx, uint32_t offset, uint32_t *value)
{
    (void)ctx;
    if (offset > 0x40 || (offset & 3)) return -1;
    *value = regs[offset / 4];
    if (offset == 0x40 && corrupt_scratch && ++scratch_reads == 2) *value ^= 1;
    ++reads;
    return 0;
}

static int fake_write(void *ctx, uint32_t offset, uint32_t value)
{
    (void)ctx;
    if (offset != 0x40) return -1;
    regs[16] = value;
    ++writes;
    return 0;
}

static int fake_barrier(void *ctx)
{
    (void)ctx;
    ++barriers;
    return 0;
}

int main(void)
{
    opp_common_io io = {0, fake_read, fake_write, fake_barrier};
    opp_common_info info;
    regs[0] = OPP_COMMON_MAGIC;
    regs[1] = OPP_COMMON_ABI;
    regs[12] = 0xf;
    regs[13] = 0x5;
    regs[16] = 0x1234abcd;
    assert(opp_common_check(&io) == 0);
    assert(opp_common_get_info(&io, &info) == 0);
    assert(info.site_present == 0xf && info.site_ready == 5);
    assert(opp_common_self_test(&io) == 0);
    assert(regs[16] == 0x1234abcd && writes == 6 && barriers == 6);
    corrupt_scratch = 1;
    scratch_reads = 0;
    assert(opp_common_self_test(&io) != 0);
    assert(regs[16] == 0x1234abcd);
    corrupt_scratch = 0;
    regs[13] = 0x10;
    assert(opp_common_get_info(&io, &info) != 0);
    regs[13] = 0;
    regs[0] = 0;
    assert(opp_common_check(&io) != 0);
    assert(reads > 0);
    puts("OPP common C host-only PASS");
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * HOST-only compatibility test using an explicitly labeled fake OpenOCD
 * swd.h declaration, NOT real OpenOCD linkage or a physical SWD target.
 */
#include "../plasma_swd_fifo_core.h"
#include <jtag/swd.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern int plasma_swd_openocd5088_bind(struct plasma_swd_fifo *site);
extern const struct swd_driver plasma_swd_openocd5088_ops;

struct mock {
    uint32_t id, mode, enabled, meta, rx, levels, cmd, swj_len, calls;
    uint32_t ack, status, write_count, barrier_count;
};

static int rd(void *ctx, uint32_t addr, uint32_t *val)
{
    struct mock *m = ctx;
    if (addr < PLASMA_SWD_SITE1_BASE ||
        addr >= PLASMA_SWD_SITE1_BASE + 4096u)
        return -1;
    switch (addr - PLASMA_SWD_SITE1_BASE) {
    case 0: *val = m->id; break;
    case 0x04: *val = m->enabled; break;
    case 0x18: *val = m->meta; break;
    case 0x1C: *val = m->rx; break;
    case 0x24: *val = m->levels; break;
    case 0x38: *val = m->mode; break;
    default: *val = 0; break;
    }
    return 0;
}

static int wr(void *ctx, uint32_t addr, uint32_t val)
{
    struct mock *m = ctx;
    if (addr < PLASMA_SWD_SITE1_BASE ||
        addr >= PLASMA_SWD_SITE1_BASE + 4096u)
        return -1;
    const uint32_t off = addr - PLASMA_SWD_SITE1_BASE;
    m->write_count++;
    if (off == 0x38) m->mode = val;
    if (off == 0x28) m->enabled = val & 1u;
    if (off == 0x64) m->swj_len = val;
    if (off == 0x14) {
        m->cmd = val & 0x1ffu;
        m->calls++;
        const bool swj = (val & 0x100u) != 0;
        const bool reading = !swj && (val & 2u) != 0;
        const uint32_t ack = m->ack ? m->ack : (swj ? 0u : 1u);
        m->meta = (val & 0xffff0000u) | (ack << 4)
                  | (reading ? 0x80u : 0u) | m->status;
        m->rx = 0x1BA01477u;
        m->levels = 2u;
    }
    if (off == 0x20u)
        m->levels = 0;
    return 0;
}

static int mb(void *ctx)
{
    struct mock *m = ctx;
    m->barrier_count++;
    return 0;
}

int main(void)
{
    struct mock m = {.id = 0x00050001u};
    struct plasma_swd_fifo site;
    struct plasma_swd_word_io ops = {
        .ctx = &m, .read32 = rd, .write32 = wr, .write_barrier = mb,
    };
    assert(plasma_swd_fifo_init(&site, &ops, 1, 50u) == 0);
    assert(plasma_swd_fifo_admit(&site) == 0);
    assert(plasma_swd_openocd5088_bind(&site) == ERROR_OK);
    assert(plasma_swd_openocd5088_bind(&site) == ERROR_FAIL);
    assert(plasma_swd_openocd5088_ops.init() == ERROR_OK);
    uint32_t value = 0xCAFEBABEu;
    assert(plasma_swd_openocd5088_ops.read_reg(0x24u, &value, 0u) == ERROR_OK);
    assert(plasma_swd_openocd5088_ops.write_reg(0x3Au, 0xDEADBEEFu, 0u) == ERROR_OK);
    assert(plasma_swd_openocd5088_ops.run() == ERROR_OK);
    assert(value == 0x1BA01477u && m.calls == 2u && m.cmd == 0x0Du);
    assert(plasma_swd_openocd5088_ops.switch_seq(JTAG_TO_SWD) == ERROR_OK);
    assert(plasma_swd_openocd5088_ops.run() == ERROR_OK);
    assert(m.swj_len == 136u && m.calls == 3u);
    assert(plasma_swd_openocd5088_ops.read_reg(0x24u, &value, 1u) == ERROR_FAIL);
    assert(m.calls == 3u);
    m.ack = 2u;
    m.status = 3u;
    assert(plasma_swd_openocd5088_ops.read_reg(0x24u, &value, 0u) == ERROR_OK);
    assert(plasma_swd_openocd5088_ops.run() == ERROR_WAIT);
    assert(value == 0x1BA01477u);
    assert(m.calls == 4u);
    assert(plasma_swd_openocd5088_ops.init() == ERROR_FAIL);
    assert(m.write_count == m.barrier_count);
    puts("PLASMA_OPENOCD5088_CALLBACK_SHIM_HOST_ONLY_PASS");
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only C test: every bus operation is injected fake, no real MMIO.
 */
#include "../plasma_swd_fifo_core.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct fake_bus {
    uint32_t base, mode, status, meta, rx, levels, pushed_cmd;
    uint32_t swj_len, stage[8], push_count, word_writes, barriers;
    uint32_t fail_barrier, fail_read, ack, completion_status;
    uint32_t fail_write_on_push;
};

static int fake_read(void *ctx, uint32_t address, uint32_t *v)
{
    struct fake_bus *f = ctx;
    if (f->fail_read || !v || address < f->base || address >= f->base + 4096u)
        return -1;
    const uint32_t off = address - f->base;
    switch (off) {
    case 0x00u: *v = PLASMA_SWD_ABI_V5 |
        (f->base == PLASMA_SWD_SITE1_BASE ? 1u : 2u); break;
    case 0x04u: *v = f->status; break;
    case 0x18u: *v = f->meta; break;
    case 0x1Cu: *v = f->rx; break;
    case 0x24u: *v = f->levels; break;
    case 0x38u: *v = f->mode; break;
    default: *v = 0; break;
    }
    return 0;
}

static int fake_write(void *ctx, uint32_t address, uint32_t v)
{
    struct fake_bus *f = ctx;
    if (address < f->base || address >= f->base + 4096u)
        return -1;
    const uint32_t off = address - f->base;
    if (f->fail_write_on_push && off == 0x14u)
        return -1;
    ++f->word_writes;
    if (off == 0x38u)
        f->mode = v;
    if (off == 0x28u)
        f->status = v & 1u;
    if (off == 0x64u)
        f->swj_len = v;
    if (off >= 0x44u && off <= 0x60u)
        f->stage[(off - 0x44u) / 4u] = v;
    if (off == 0x14u) {
        f->pushed_cmd = v & 0x1FFu;
        ++f->push_count;
        const bool swj = (v & 0x100u) != 0;
        const bool reading = !swj && (v & 2u) != 0;
        const uint32_t ack = f->ack ? f->ack : (swj ? 0u : 1u);
        f->meta = (v & 0xFFFF0000u) | (uint32_t)(reading ? 0x80u : 0u) |
                 (ack << 4) | f->completion_status;
        f->rx = 0x1BA01477u;
        f->levels = 2u;
    }
    if (off == 0x20u) {
        assert(v == f->meta >> 16);
        f->levels = 0u;
    }
    return 0;
}

static int fake_barrier(void *ctx)
{
    struct fake_bus *f = ctx;
    ++f->barriers;
    return f->fail_barrier ? -1 : 0;
}

static void setup(struct fake_bus *f, struct plasma_swd_fifo *s,
                  unsigned int site)
{
    memset(f, 0, sizeof(*f));
    f->base = site == 1u ? PLASMA_SWD_SITE1_BASE : PLASMA_SWD_SITE2_BASE;
    const struct plasma_swd_word_io ops = {
        .ctx = f, .read32 = fake_read,
        .write32 = fake_write, .write_barrier = fake_barrier,
    };
    assert(plasma_swd_fifo_init(s, &ops, site, 8u) == 0);
    assert(f->word_writes == 0u); /* inert constructor */
    assert(plasma_swd_fifo_queue_read(s, 0x24u, &f->rx, 0u) ==
           PLASMA_SWD_NOT_READY);
    assert(plasma_swd_fifo_admit(s) == 0);
}

static void test_two_sites_ordered_reads_and_writes(void)
{
    struct fake_bus a, b;
    struct plasma_swd_fifo site1, site2;
    setup(&a, &site1, 1);
    setup(&b, &site2, 2);
    uint32_t got1 = 0, got2 = 0;
    assert(plasma_swd_fifo_queue_read(&site1, 0x24u, &got1, 0u) == 0);
    assert(plasma_swd_fifo_queue_write(&site1, 0x3Au, 0xDEADBEEFu, 0u) == 0);
    assert(plasma_swd_fifo_queue_read(&site2, 0x24u, &got2, 0u) == 0);
    assert(a.push_count == 0u && b.push_count == 0u);
    assert(plasma_swd_fifo_run(&site1) == 0);
    assert(plasma_swd_fifo_run(&site2) == 0);
    assert(got1 == 0x1BA01477u && got2 == got1);
    assert(a.push_count == 2u && b.push_count == 1u);
    assert(a.pushed_cmd == 0x0Du && b.pushed_cmd == 0x02u);
    assert(a.word_writes == a.barriers);
    assert(b.word_writes == b.barriers);
    assert(plasma_swd_fifo_run(&site1) == 0);
    assert(a.push_count == 2u); /* no replay */
}

static void test_exact_atomic_swj_and_negative_inputs(void)
{
    struct fake_bus f;
    struct plasma_swd_fifo site;
    setup(&f, &site, 1);
    const uint8_t swj136[17] = {
        0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0x9E,0xE7,
        0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0x00,
    };
    assert(plasma_swd_fifo_queue_swj(&site, swj136, 136u) == 0);
    assert(plasma_swd_fifo_run(&site) == 0);
    assert(f.swj_len == 136u);
    assert(f.stage[0] == 0xFFFFFFFFu);
    assert(f.stage[1] == 0x9EFFFFFFu);
    assert(f.pushed_cmd == (0x100u | 136u));
    const uint8_t one[] = {0xFF};
    assert(plasma_swd_fifo_queue_swj(&site, one, 1u) ==
           PLASMA_SWD_BAD_ARG); /* nonzero padding */
    assert(plasma_swd_fifo_queue_swj(&site, one, 0u) ==
           PLASMA_SWD_BAD_ARG);
    assert(plasma_swd_fifo_queue_read(&site, 0x04u, &f.rx, 0u) ==
           PLASMA_SWD_BAD_ARG); /* parity/direction mismatch */
    assert(plasma_swd_fifo_queue_read(&site, 0x25u, &f.rx, 0u) ==
           PLASMA_SWD_BAD_ARG);
    assert(plasma_swd_fifo_queue_read(&site, 0x24u, NULL, 0u) ==
           PLASMA_SWD_BAD_ARG);
    assert(plasma_swd_fifo_queue_read(&site, 0x24u, &f.rx, 1u) ==
           PLASMA_SWD_UNSUPPORTED);
    assert(plasma_swd_fifo_queue_write(&site, 0x18u, 1u, 0u) ==
           PLASMA_SWD_UNSUPPORTED); /* DP TARGETSEL no-ACK */
}

static void test_wait_fault_no_replay_and_pointer_safety(void)
{
    for (unsigned int mode = 0; mode < 2; ++mode) {
        struct fake_bus f;
        struct plasma_swd_fifo s;
        setup(&f, &s, 1);
        f.ack = mode ? 4u : 2u;
        f.completion_status = mode ? 4u : 3u;
        uint32_t read_result = 0xC0FFEEu;
        assert(plasma_swd_fifo_queue_read(&s, 0x24u, &read_result, 0u) == 0);
        assert(plasma_swd_fifo_queue_write(&s, 0x3Au, 0xAABBCCDDu, 0u) == 0);
        assert(plasma_swd_fifo_run(&s) ==
               (mode ? PLASMA_SWD_ACK_FAULT : PLASMA_SWD_ACK_WAIT));
        assert(read_result == 0xC0FFEEu); /* not published on failure */
        assert(f.push_count == 1u);
        assert(plasma_swd_fifo_run(&s) == PLASMA_SWD_NOT_READY);
        assert(f.push_count == 1u);
    }
    struct fake_bus f;
    struct plasma_swd_fifo s;
    setup(&f, &s, 2);
    f.fail_barrier = 1u;
    assert(plasma_swd_fifo_queue_write(&s, 0x3Au, 2u, 0u) == 0);
    assert(plasma_swd_fifo_run(&s) == PLASMA_SWD_IO_UNCERTAIN);
    assert(s.blocked && !s.admitted);
    assert(plasma_swd_fifo_run(&s) == PLASMA_SWD_NOT_READY);
    assert(f.push_count == 0u); /* barrier failed after TX, before PUSH */
}

static void test_fifo_queue_bounds_and_tags(void)
{
    struct fake_bus f;
    struct plasma_swd_fifo s;
    setup(&f, &s, 1);
    for (unsigned int i = 0; i < 16; ++i)
        assert(plasma_swd_fifo_queue_write(&s, 0x3Au, i, 0u) == 0);
    assert(plasma_swd_fifo_queue_write(&s, 0x3Au, 33, 0u) ==
           PLASMA_SWD_QUEUE_FULL);
    assert(plasma_swd_fifo_run(&s) == 0);
    assert(f.push_count == 16u);
    s.next_tag = 65535u;
    assert(plasma_swd_fifo_queue_write(&s, 0x3Au, 0u, 0u) == 0);
    assert(plasma_swd_fifo_queue_write(&s, 0x3Au, 1u, 0u) == 0);
    const uint32_t before = f.push_count;
    assert(plasma_swd_fifo_run(&s) == PLASMA_SWD_NOT_READY);
    assert(f.push_count == before);
}

static void test_new_fifo_rejects_prior_normal_mode_and_unknown_completion(void)
{
    /* A fresh FIFO instance may follow an Owner killed by SIGKILL. The
     * prior process's FIFO state is gone, while synthetic PL still reports
     * NORMAL with an unconsumed completion. Admission must not clear it or
     * permit a write. This is not persistent recovery evidence. */
    struct fake_bus f = {0};
    struct plasma_swd_fifo new_owner;
    f.base = PLASMA_SWD_SITE1_BASE;
    f.mode = 1u;
    f.status = 1u;
    f.levels = 2u;
    const struct plasma_swd_word_io io = {
        .ctx = &f, .read32 = fake_read,
        .write32 = fake_write, .write_barrier = fake_barrier,
    };
    assert(plasma_swd_fifo_init(&new_owner, &io, 1u, 8u) == 0);
    assert(plasma_swd_fifo_admit(&new_owner) == PLASMA_SWD_NOT_READY);
    assert(new_owner.blocked && !new_owner.admitted);
    assert(f.word_writes == 0u && f.push_count == 0u);
    assert(plasma_swd_fifo_queue_write(&new_owner, 0x3Au, 0x1234u, 0u)
           == PLASMA_SWD_NOT_READY);
}

int main(void)
{
    test_two_sites_ordered_reads_and_writes();
    test_exact_atomic_swj_and_negative_inputs();
    test_wait_fault_no_replay_and_pointer_safety();
    test_fifo_queue_bounds_and_tags();
    test_new_fifo_rejects_prior_normal_mode_and_unknown_completion();
    puts("PLASMA_NATIVE_SWD_C_HOST_ONLY_PASS");
    return 0;
}

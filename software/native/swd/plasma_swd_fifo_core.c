/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only native SWD FIFO core for candidate ABI v5.
 * Never opens MMIO, loads an Image, claims a Site or toggles a debug GPIO.
 * Requires externally admitted exclusive PS Site lease + safe voltage/manifest.
 */
#include "plasma_swd_fifo_core.h"

#include <stddef.h>
#include <string.h>

#define R_ID 0x00u
#define R_STATUS 0x04u
#define R_TX 0x10u
#define R_PUSH 0x14u
#define R_META 0x18u
#define R_RX 0x1Cu
#define R_POP 0x20u
#define R_LEVELS 0x24u
#define R_CONTROL 0x28u
#define R_ERROR 0x2Cu
#define R_IRQ_ENABLE 0x30u
#define R_MODE 0x38u
#define R_SWJ_WORD0 0x44u
#define R_SWJ_LENGTH 0x64u
#define R_IDLE_CYCLES 0x68u

static int fault(struct plasma_swd_fifo *s, int code)
{
    s->blocked = true;
    s->admitted = false;
    s->count = 0;
    return code;
}

static int read_word(struct plasma_swd_fifo *s, uint32_t off, uint32_t *value)
{
    if (s->io.read32(s->io.ctx, s->base + off, value))
        return fault(s, PLASMA_SWD_IO_UNCERTAIN);
    return PLASMA_SWD_OK;
}

static int write_word(struct plasma_swd_fifo *s, uint32_t off, uint32_t value)
{
    if (s->io.write32(s->io.ctx, s->base + off, value))
        return fault(s, PLASMA_SWD_IO_UNCERTAIN);
    if (s->io.write_barrier(s->io.ctx))
        return fault(s, PLASMA_SWD_IO_UNCERTAIN);
    return PLASMA_SWD_OK;
}

int plasma_swd_fifo_init(struct plasma_swd_fifo *s,
                         const struct plasma_swd_word_io *io,
                         unsigned int site_id, uint32_t max_polls)
{
    if (!s || !io || !io->read32 || !io->write32 || !io->write_barrier ||
        (site_id != 1u && site_id != 2u) ||
        max_polls == 0 || max_polls > 1000000u)
        return PLASMA_SWD_BAD_ARG;
    memset(s, 0, sizeof(*s));
    s->io = *io;
    s->base = site_id == 1u ? PLASMA_SWD_SITE1_BASE : PLASMA_SWD_SITE2_BASE;
    s->max_polls = max_polls;
    s->next_tag = 1;
    s->idle_cycles = PLASMA_SWD_IDLE_DEFAULT;
    return PLASMA_SWD_OK;
}

int plasma_swd_fifo_admit(struct plasma_swd_fifo *s)
{
    uint32_t id = 0, mode = 0, status = 0;
    if (!s || s->blocked || s->admitted || !s->io.read32)
        return PLASMA_SWD_NOT_READY;
    if (read_word(s, R_ID, &id) || id !=
        (PLASMA_SWD_ABI_V5 | (s->base == PLASMA_SWD_SITE1_BASE ? 1u : 2u)))
        return fault(s, PLASMA_SWD_BAD_RESPONSE);
    if (read_word(s, R_MODE, &mode) || mode != 0u)
        return fault(s, PLASMA_SWD_NOT_READY);
    if (write_word(s, R_MODE, 1u) ||
        write_word(s, R_IRQ_ENABLE, 0u) ||
        write_word(s, R_CONTROL, 1u))
        return PLASMA_SWD_IO_UNCERTAIN;
    if (read_word(s, R_MODE, &mode) || read_word(s, R_STATUS, &status) ||
        mode != 1u || !(status & 1u))
        return fault(s, PLASMA_SWD_BAD_RESPONSE);
    /* MODE was 0 before this admission: the RTL restored IDLE_CYCLES=8. */
    s->idle_cycles = PLASMA_SWD_IDLE_DEFAULT;
    s->admitted = true;
    return PLASMA_SWD_OK;
}

static int decode_swd(uint8_t cmd, bool read, uint8_t *private_cmd)
{
    uint8_t x = cmd & 0x1Eu;
    unsigned int parity = 0;
    for (; x; x >>= 1)
        parity ^= x & 1u;
    if ((cmd & 0xC1u) || ((cmd >> 5) & 1u) != parity ||
        (bool)(cmd & 4u) != read)
        return PLASMA_SWD_BAD_ARG;
    const uint8_t ap = (cmd >> 1) & 1u;
    const uint8_t address_index = (cmd >> 3) & 3u;
    if (!ap && !read && address_index == 3u)
        return PLASMA_SWD_UNSUPPORTED; /* DPv2 TARGETSEL: no ACK */
    *private_cmd = ap | ((uint8_t)read << 1) | (address_index << 2);
    return PLASMA_SWD_OK;
}

/* OpenOCD queues whole memory blocks (hundreds of transfers) before one
 * run(). When the software queue is full, execute it now, as bitbang and
 * CMSIS-DAP adapters do; a failure is also reported by the next run(). */
static int reserve(struct plasma_swd_fifo *s)
{
    if (s->count < PLASMA_SWD_MAX_QUEUE)
        return PLASMA_SWD_OK;
    const int rc = plasma_swd_fifo_run(s);
    if (rc)
        s->deferred_rc = rc;
    return rc;
}

static int queue_transfer(struct plasma_swd_fifo *s, uint8_t cmd, bool read,
                          uint32_t data, uint32_t *dst, uint32_t hint)
{
    uint8_t private_cmd = 0;
    if (!s || !s->admitted || s->blocked)
        return PLASMA_SWD_NOT_READY;
    /* OpenOCD swd_driver.read_reg() may pass value == NULL to discard a
     * read (e.g. dap_dp_init's DP CTRL/STAT read). The transfer still runs
     * with full ACK/parity checking; only publication is skipped. */
    int status = decode_swd(cmd, read, &private_cmd);
    if (status)
        return status;
    /* OpenOCD passes ap->memaccess_tck (default 255; Cortex-M examine sets
     * 8) for every AP transfer and 0 for DP. Each command already ends with
     * the RTL's IDLE_CYCLES clocks, so request max(8, hint), saturated. */
    uint8_t idle = PLASMA_SWD_IDLE_DEFAULT;
    if ((private_cmd & 1u) && hint > PLASMA_SWD_IDLE_DEFAULT)
        idle = hint > PLASMA_SWD_IDLE_MAX ? PLASMA_SWD_IDLE_MAX : (uint8_t)hint;
    status = reserve(s);
    if (status)
        return status;
    struct plasma_swd_queue_op *op = &s->pending[s->count++];
    memset(op, 0, sizeof(*op));
    op->private_command = private_cmd;
    op->read = read;
    op->value = data;
    op->destination = dst;
    op->idle_cycles = idle;
    return PLASMA_SWD_OK;
}

int plasma_swd_fifo_queue_read(struct plasma_swd_fifo *s, uint8_t cmd,
                              uint32_t *dst, uint32_t hint)
{
    return queue_transfer(s, cmd, true, 0, dst, hint);
}

int plasma_swd_fifo_queue_write(struct plasma_swd_fifo *s, uint8_t cmd,
                               uint32_t value, uint32_t hint)
{
    return queue_transfer(s, cmd, false, value, NULL, hint);
}

int plasma_swd_fifo_queue_line_reset(struct plasma_swd_fifo *s)
{
    if (!s || !s->admitted || s->blocked)
        return PLASMA_SWD_NOT_READY;
    const int status = reserve(s);
    if (status)
        return status;
    struct plasma_swd_queue_op *op = &s->pending[s->count++];
    memset(op, 0, sizeof(*op));
    op->is_swj = true;
    op->bit_count = 0; /* RTL 64-clock line-reset encoding */
    op->idle_cycles = PLASMA_SWD_IDLE_DEFAULT;
    return PLASMA_SWD_OK;
}

int plasma_swd_fifo_recover_off(struct plasma_swd_fifo *s, int *recovered)
{
    uint32_t status = 0, levels = 0, meta = 0, mode = 0;
    if (recovered)
        *recovered = 0;
    if (!s || !s->io.read32 || !s->io.write32 || !s->io.write_barrier)
        return PLASMA_SWD_BAD_ARG;
    s->count = 0; /* software queue is discarded, never replayed */
    if (s->io.read32(s->io.ctx, s->base + R_MODE, &mode))
        return PLASMA_SWD_IO_UNCERTAIN;
    if (mode == 0u)
        return PLASMA_SWD_OK; /* already OFF: no write at all */
    if (mode != 1u ||
        s->io.read32(s->io.ctx, s->base + R_STATUS, &status) ||
        ((status >> 4) & 3u) != 1u || (status & 2u))
        return PLASMA_SWD_NOT_READY; /* invalid, uncertain or busy */
    if (recovered)
        *recovered = 1;
    if ((status & 8u) &&
        (s->io.write32(s->io.ctx, s->base + R_CONTROL, 4u) ||
         s->io.write_barrier(s->io.ctx)))
        return PLASMA_SWD_IO_UNCERTAIN; /* fault-only command discard */
    for (unsigned int i = 0; i <= PLASMA_SWD_MAX_QUEUE; ++i) {
        if (s->io.read32(s->io.ctx, s->base + R_LEVELS, &levels))
            return PLASMA_SWD_IO_UNCERTAIN;
        if (!(levels & 2u))
            break;
        if (i == PLASMA_SWD_MAX_QUEUE ||
            s->io.read32(s->io.ctx, s->base + R_META, &meta) ||
            s->io.write32(s->io.ctx, s->base + R_POP, meta >> 16) ||
            s->io.write_barrier(s->io.ctx))
            return PLASMA_SWD_IO_UNCERTAIN;
    }
    if (levels != 0u)
        return PLASMA_SWD_NOT_READY;
    if ((status & 8u) &&
        (s->io.write32(s->io.ctx, s->base + R_ERROR, 1u) ||
         s->io.write_barrier(s->io.ctx)))
        return PLASMA_SWD_IO_UNCERTAIN;
    if (s->io.write32(s->io.ctx, s->base + R_CONTROL, 0u) ||
        s->io.write_barrier(s->io.ctx) ||
        s->io.read32(s->io.ctx, s->base + R_STATUS, &status))
        return PLASMA_SWD_IO_UNCERTAIN;
    /* MODE is written only after STATUS proves NORMAL, disabled, idle,
     * no retained response and no latched fault. */
    if ((status & 0x3Fu) != 0x10u)
        return PLASMA_SWD_IO_UNCERTAIN;
    if (s->io.write32(s->io.ctx, s->base + R_MODE, 0u) ||
        s->io.write_barrier(s->io.ctx) ||
        s->io.read32(s->io.ctx, s->base + R_MODE, &mode) || mode != 0u)
        return PLASMA_SWD_IO_UNCERTAIN;
    s->admitted = false;
    return PLASMA_SWD_OK;
}

int plasma_swd_fifo_queue_swj(struct plasma_swd_fifo *s,
                             const uint8_t *payload, uint16_t count)
{
    if (!s || !s->admitted || s->blocked)
        return PLASMA_SWD_NOT_READY;
    if (!payload || count == 0 || count > 256)
        return PLASMA_SWD_BAD_ARG;
    const uint16_t len = (count + 7u) / 8u;
    if ((count & 7u) && (payload[len - 1u] >> (count & 7u)))
        return PLASMA_SWD_BAD_ARG;
    const int status = reserve(s);
    if (status)
        return status;
    struct plasma_swd_queue_op *op = &s->pending[s->count++];
    memset(op, 0, sizeof(*op));
    op->is_swj = true;
    op->bit_count = count;
    op->idle_cycles = PLASMA_SWD_IDLE_DEFAULT;
    op->private_command = 0x00; /* SWJ has bit8 enabled at PUSH */
    memcpy(op->swj_bytes, payload, len);
    return PLASMA_SWD_OK;
}

static int push_one(struct plasma_swd_fifo *s,
                    const struct plasma_swd_queue_op *op, uint32_t tag)
{
    uint32_t data = op->value;
    uint32_t command = op->private_command;
    /* Snapshotted by the RTL at PUSH; write only on change, so a session that
     * never needs more than 8 never touches the register. */
    if (op->idle_cycles != s->idle_cycles) {
        if (write_word(s, R_IDLE_CYCLES, op->idle_cycles))
            return PLASMA_SWD_IO_UNCERTAIN;
        s->idle_cycles = op->idle_cycles;
    }
    if (op->is_swj) {
        command = 0x100u | (op->bit_count & 0xFFu);
        if (op->bit_count <= 32u) {
            data = 0u;
            for (unsigned int i = 0; i < 4; ++i)
                data |= ((uint32_t)op->swj_bytes[i]) << (8u * i);
        } else {
            /* Staging uses full 256 bits; accepted PUSH snapshots atomically. */
            for (unsigned int word = 0; word < 8; ++word) {
                uint32_t value = 0;
                for (unsigned int byte = 0; byte < 4; ++byte)
                    value |= ((uint32_t)op->swj_bytes[word * 4u + byte])
                             << (8u * byte);
                if (write_word(s, R_SWJ_WORD0 + 4u * word, value))
                    return PLASMA_SWD_IO_UNCERTAIN;
            }
            if (write_word(s, R_SWJ_LENGTH, op->bit_count))
                return PLASMA_SWD_IO_UNCERTAIN;
        }
    }
    if (write_word(s, R_TX, data) ||
        write_word(s, R_PUSH, (tag << 16) | command))
        return PLASMA_SWD_IO_UNCERTAIN;
    return PLASMA_SWD_OK;
}

static int take_one(struct plasma_swd_fifo *s,
                    const struct plasma_swd_queue_op *op, uint32_t tag,
                    uint32_t *data)
{
    uint32_t levels = 0, meta = 0, raw_data = 0;
    uint32_t n;
    for (n = 0; n < s->max_polls; ++n) {
        if (read_word(s, R_LEVELS, &levels))
            return PLASMA_SWD_IO_UNCERTAIN;
        if (levels & 2u)
            break;
    }
    if (n == s->max_polls) {
        s->last_meta = 0xFFFFFFFFu; /* no completion observed */
        s->last_levels = levels;
        return fault(s, PLASMA_SWD_BAD_RESPONSE);
    }
    if (read_word(s, R_META, &meta) || read_word(s, R_RX, &raw_data))
        return PLASMA_SWD_IO_UNCERTAIN;
    s->last_meta = meta;
    s->last_levels = levels;
    if ((meta >> 16) != tag)
        return fault(s, PLASMA_SWD_BAD_RESPONSE);
    if (!op->is_swj) {
        const uint32_t ack = (meta >> 4) & 7u;
        if (ack == 2u && (meta & 0xFu) == 3u) {
            /* WAIT: the transfer was not accepted; the caller may retry.
             * Release the retained completion first. */
            if (write_word(s, R_POP, tag))
                return PLASMA_SWD_IO_UNCERTAIN;
            return PLASMA_SWD_ACK_WAIT;
        }
        if (ack == 4u && (meta & 0xFu) == 4u)
            return fault(s, PLASMA_SWD_ACK_FAULT);
        if (ack != 1u)
            return fault(s, PLASMA_SWD_BAD_RESPONSE);
    }
    if ((meta & 0xFu) != 0u || (bool)(meta & 0x80u) != op->read)
        return fault(s, PLASMA_SWD_BAD_RESPONSE);
    if (write_word(s, R_POP, tag))
        return PLASMA_SWD_IO_UNCERTAIN;
    *data = raw_data;
    return PLASMA_SWD_OK;
}

/* 16-bit nonzero completion tags; one command is in flight at a time, so
 * wrapping 65535 -> 1 cannot alias a retained completion. */
static uint32_t take_tag(struct plasma_swd_fifo *s)
{
    const uint32_t tag = s->next_tag;
    s->next_tag = tag >= 65535u ? 1u : tag + 1u;
    return tag;
}

/* One transfer; on ACK WAIT clear sticky/overrun via DP ABORT
 * (ORUNERRCLR|WDERRCLR|STKERRCLR|STKCMPCLR) and retry, like OpenOCD's
 * bitbang adapter. The waited transfer was never accepted: no replay. */
static int exec_one(struct plasma_swd_fifo *s,
                    const struct plasma_swd_queue_op *op, uint32_t *data)
{
    static const struct plasma_swd_queue_op abort_op = {
        .private_command = 0x00u, .read = false, .value = 0x1Eu,
        .idle_cycles = PLASMA_SWD_IDLE_DEFAULT,
    };
    for (unsigned int attempt = 0;; ++attempt) {
        uint32_t tag = take_tag(s);
        if (push_one(s, op, tag))
            return PLASMA_SWD_IO_UNCERTAIN;
        const int rc = take_one(s, op, tag, data);
        if (rc != PLASMA_SWD_ACK_WAIT)
            return rc;
        if (attempt == PLASMA_SWD_WAIT_RETRIES)
            return fault(s, PLASMA_SWD_ACK_WAIT);
        uint32_t ignored = 0;
        tag = take_tag(s);
        if (push_one(s, &abort_op, tag))
            return PLASMA_SWD_IO_UNCERTAIN;
        const int arc = take_one(s, &abort_op, tag, &ignored);
        if (arc)
            return arc == PLASMA_SWD_ACK_WAIT ? fault(s, arc) : arc;
    }
}

int plasma_swd_fifo_run(struct plasma_swd_fifo *s)
{
    uint32_t read_values[PLASMA_SWD_MAX_QUEUE] = {0};
    if (!s || !s->admitted || s->blocked)
        return PLASMA_SWD_NOT_READY;
    if (s->deferred_rc) {
        const int rc = s->deferred_rc;
        s->deferred_rc = 0;
        s->count = 0;
        return rc;
    }
    const uint32_t count = s->count;
    s->count = 0; /* consume immediately, never replay accepted commands */
    for (uint32_t i = 0; i < count; ++i) {
        uint32_t value = 0;
        const int rc = exec_one(s, &s->pending[i], &value);
        if (rc)
            return rc;
        read_values[i] = value;
    }
    /* Result pointers are published only if the WHOLE queue succeeded. */
    for (uint32_t i = 0; i < count; ++i)
        if (s->pending[i].read && s->pending[i].destination)
            *s->pending[i].destination = read_values[i];
    return PLASMA_SWD_OK;
}

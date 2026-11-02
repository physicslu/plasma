/* SPDX-License-Identifier: GPL-2.0-or-later
 * PLASMA Host-only native C SWD FIFO contract. No device/FPGA access on init.
 * OpenOCD 5088db4c callbacks require a separate integration/owner gate.
 */
#ifndef PLASMA_SWD_FIFO_CORE_H
#define PLASMA_SWD_FIFO_CORE_H

#include <stdbool.h>
#include <stdint.h>

#define PLASMA_SWD_MAX_QUEUE 16u
#define PLASMA_SWD_ABI_V5 0x00050000u
#define PLASMA_SWD_SITE1_BASE 0x43C01000u
#define PLASMA_SWD_SITE2_BASE 0x43C02000u

enum plasma_swd_result {
    PLASMA_SWD_OK = 0,
    PLASMA_SWD_BAD_ARG = -1,
    PLASMA_SWD_NOT_READY = -2,
    PLASMA_SWD_IO_UNCERTAIN = -3,
    PLASMA_SWD_BAD_RESPONSE = -4,
    PLASMA_SWD_ACK_WAIT = -5,
    PLASMA_SWD_ACK_FAULT = -6,
    PLASMA_SWD_QUEUE_FULL = -7,
    PLASMA_SWD_UNSUPPORTED = -8,
};

struct plasma_swd_word_io {
    void *ctx;
    int (*read32)(void *ctx, uint32_t address, uint32_t *value);
    int (*write32)(void *ctx, uint32_t address, uint32_t value);
    int (*write_barrier)(void *ctx);
};

struct plasma_swd_queue_op {
    uint8_t private_command;
    bool is_swj;
    bool read;
    uint32_t value;
    uint32_t *destination;
    uint16_t bit_count;
    uint8_t swj_bytes[32];
};

struct plasma_swd_fifo {
    struct plasma_swd_word_io io;
    uint32_t base;
    uint32_t max_polls;
    uint32_t next_tag;
    uint32_t count;
    bool admitted;
    bool blocked;
    struct plasma_swd_queue_op pending[PLASMA_SWD_MAX_QUEUE];
};

/* Construction performs no read, write, mapping or lease acquisition. */
int plasma_swd_fifo_init(struct plasma_swd_fifo *s,
                         const struct plasma_swd_word_io *io,
                         unsigned int site_id, uint32_t max_polls);

/* Caller must ALREADY own the Image/Manifest, electrical and Site lease. */
int plasma_swd_fifo_admit(struct plasma_swd_fifo *s);

/* OpenOCD swd_cmd() v5088 layout, NOT the FPGA 9-bit command. */
int plasma_swd_fifo_queue_read(struct plasma_swd_fifo *s, uint8_t cmd,
                              uint32_t *destination, uint32_t ap_delay_hint);
int plasma_swd_fifo_queue_write(struct plasma_swd_fifo *s, uint8_t cmd,
                               uint32_t value, uint32_t ap_delay_hint);

/* Full source-defined LSB-first SWJ payload; no arbitrary GPIO toggles. */
int plasma_swd_fifo_queue_swj(struct plasma_swd_fifo *s,
                             const uint8_t *payload, uint16_t count);

/* Complete bounded ordered transfers; no auto-retry, no ACK fabrication. */
int plasma_swd_fifo_run(struct plasma_swd_fifo *s);
#endif

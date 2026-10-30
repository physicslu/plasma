/* SPDX-License-Identifier: GPL-2.0-or-later
 * HOST TEST DECLARATIONS MIRRORING pinned OpenOCD 5088db4c swd.h.
 * This is NOT the original OpenOCD header. Exact-source native build remains
 * a separate blocking CI requirement. Synthetic SWJ patterns: not HIL proof.
 */
#ifndef PLASMA_TEST_OPENOCD_SWD_SHIM_H
#define PLASMA_TEST_OPENOCD_SWD_SHIM_H
#include <stdint.h>
#include <stdbool.h>
enum swd_special_seq {
    LINE_RESET, JTAG_TO_SWD, JTAG_TO_DORMANT, SWD_TO_JTAG,
    SWD_TO_DORMANT, DORMANT_TO_SWD, DORMANT_TO_JTAG,
};
#define ERROR_OK 0
#define ERROR_FAIL (-1)
#define ERROR_WAIT (-4)
#define ERROR_SWD_FAIL (-400)
#define ERROR_SWD_FAULT (-401)
static const uint8_t swd_seq_line_reset[] = {
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x00
};
static const unsigned int swd_seq_line_reset_len = 64;
static const uint8_t swd_seq_jtag_to_swd[] = {
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x9e,0xe7,
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x00
};
static const unsigned int swd_seq_jtag_to_swd_len = 136;
static const uint8_t swd_seq_jtag_to_dormant[] = {0xff,0x75,0x77,0x77,0x67};
static const unsigned int swd_seq_jtag_to_dormant_len = 40;
static const uint8_t swd_seq_swd_to_jtag[] = {
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x3c,0xe7,0xff
};
static const unsigned int swd_seq_swd_to_jtag_len = 80;
static const uint8_t swd_seq_swd_to_dormant[] = {
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xbc,0xe3
};
static const unsigned int swd_seq_swd_to_dormant_len = 72;
static const uint8_t swd_seq_dormant_to_swd[] = {
    0xff,0x92,0xf3,0x09,0x62,0x95,0x2d,0x85,0x86,
    0xe9,0xaf,0xdd,0xe3,0xa2,0x0e,0xbc,0x19,
    0xa0,0xf1,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x00
};
static const unsigned int swd_seq_dormant_to_swd_len = 224;
static const uint8_t swd_seq_dormant_to_jtag[] = {
    0xff,0x92,0xf3,0x09,0x62,0x95,0x2d,0x85,0x86,
    0xe9,0xaf,0xdd,0xe3,0xa2,0x0e,0xbc,0x19,
    0x00,0x00,0x00
};
static const unsigned int swd_seq_dormant_to_jtag_len = 160;
struct swd_driver {
    int (*init)(void);
    int (*switch_seq)(enum swd_special_seq);
    int (*read_reg)(uint8_t, uint32_t *, uint32_t);
    int (*write_reg)(uint8_t, uint32_t, uint32_t);
    int (*run)(void);
    int *(*trace)(bool);
};
#endif

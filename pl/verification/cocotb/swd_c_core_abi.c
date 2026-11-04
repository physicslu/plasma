/* SPDX-License-Identifier: GPL-2.0-or-later
 * Test-only ABI probe linked next to the UNMODIFIED production
 * software/native/swd/plasma_swd_fifo_core.c. It contains no control logic:
 * it only reports struct layout so the ctypes mirror cannot silently drift.
 */
#include <stddef.h>

#include "plasma_swd_fifo_core.h"

size_t plasma_swd_test_layout(unsigned int which)
{
    switch (which) {
    case 0: return sizeof(struct plasma_swd_fifo);
    case 1: return sizeof(struct plasma_swd_queue_op);
    case 2: return offsetof(struct plasma_swd_fifo, base);
    case 3: return offsetof(struct plasma_swd_fifo, deferred_rc);
    case 4: return offsetof(struct plasma_swd_fifo, blocked);
    case 5: return offsetof(struct plasma_swd_fifo, last_meta);
    case 6: return offsetof(struct plasma_swd_fifo, pending);
    default: return (size_t)-1;
    }
}

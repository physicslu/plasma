/* PLASMA Blue Pill Site-1 high-frequency WordPort data path.
 *
 * This is a deliberately small C ABI, not an independent hardware owner.
 * The protected Python process owns Root admission, FPGA/image checkpoint,
 * flock, Site lease, mmap, UNIX socket and cleanup. The caller must hold the
 * LinuxMMIO mutex and supply the already-validated mapped page for EVERY call.
 * There is no device open, address argument, FPGA operation, SWD transaction
 * algorithm, Flash operation, socket or Python callback in this file.
 *
 * The ARMv7 DMB orders CPU accesses; it cannot certify AXI completion,
 * memory attributes, electrical safety, or recover from SIGBUS/AXI hangs.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdatomic.h>

#define PLASMA_RBB_ABI 1u
#define PLASMA_RBB_MAGIC 0x50425357u
#define PLASMA_RBB_VERSION 0x00010000u

typedef struct {
    uint32_t admitted;
    uint32_t closed;
    uint32_t poisoned;
    uint32_t clock;
    uint32_t swdio;
    uint32_t oe;
    uint32_t reads;
    uint32_t writes;
} plasma_rbb_state;

enum {
    PLASMA_OK = 0,
    PLASMA_BAD_STATE = 1,
    PLASMA_BAD_ABI = 2,
    PLASMA_UNSAFE_PINS = 3,
    PLASMA_BAD_COMMAND = 4,
    PLASMA_QUIT_TRAILER = 5,
    PLASMA_BAD_BUFFER = 6
};

_Static_assert(sizeof(uint32_t) == 4, "32-bit register access required");

static inline void ordered_barrier(void) {
#if defined(__arm__) && defined(__ARM_ARCH_7A__)
    __asm__ __volatile__("dmb sy" ::: "memory");
#else
    /* Host-only model: compiler ordering, NOT a substitute for ARMv7 DMB. */
    atomic_signal_fence(memory_order_seq_cst);
#endif
}

uint32_t plasma_rbb_abi_version(void) { return PLASMA_RBB_ABI; }

uint32_t plasma_rbb_is_armv7(void) {
#if defined(__arm__) && defined(__ARM_ARCH_7A__)
    return 1u;
#else
    return 0u;
#endif
}

static inline uint32_t load_word(volatile uint32_t *page, size_t index,
                                  plasma_rbb_state *state) {
    uint32_t value = page[index];
    ++state->reads;
    return value;
}

static inline void drive(volatile uint32_t *page, plasma_rbb_state *state) {
    /* Fixed offset 0x08, with reserved bits forced to zero. */
    page[2] = state->clock | (state->swdio << 1) | (state->oe << 2);
    ++state->writes;
    ordered_barrier();
}

int plasma_rbb_admit(volatile uint32_t *page, plasma_rbb_state *state) {
    if (!page || !state || state->admitted || state->closed || state->poisoned)
        return PLASMA_BAD_STATE;
    if (load_word(page, 0, state) != PLASMA_RBB_MAGIC ||
        load_word(page, 1, state) != PLASMA_RBB_VERSION) {
        state->poisoned = 1;
        return PLASMA_BAD_ABI;
    }
    if ((load_word(page, 3, state) & 0x0eu) != 0x08u) {
        state->poisoned = 1;
        return PLASMA_UNSAFE_PINS;
    }
    state->clock = 0;
    state->swdio = 1;
    state->oe = 0;
    state->admitted = 1;
    return PLASMA_OK;
}

int plasma_rbb_close(volatile uint32_t *page, plasma_rbb_state *state) {
    if (!page || !state)
        return PLASMA_BAD_STATE;
    if (state->closed)
        return PLASMA_OK;
    if (state->admitted && !state->poisoned) {
        state->clock = 0;
        state->swdio = 1;
        state->oe = 0;
        drive(page, state);
    }
    state->admitted = 0;
    state->closed = 1;
    return PLASMA_OK;
}

int plasma_rbb_exchange(volatile uint32_t *page, plasma_rbb_state *state,
                        const uint8_t *input, size_t input_len,
                        uint8_t *output, size_t output_capacity,
                        size_t *output_len) {
    size_t used = 0;
    if (!page || !state || !output_len || (!input && input_len) ||
        (!output && output_capacity) || input_len > 4096)
        return PLASMA_BAD_BUFFER;
    *output_len = 0;
    if (!state->admitted || state->closed || state->poisoned)
        return PLASMA_BAD_STATE;
    for (size_t i = 0; i < input_len; ++i) {
        uint8_t ch = input[i];
        if (ch == 'Q') {
            (void)plasma_rbb_close(page, state);
            *output_len = used;
            return i + 1 == input_len ? PLASMA_OK : PLASMA_QUIT_TRAILER;
        }
        if (ch == 'O' || ch == 'o') {
            state->oe = ch == 'O';
            drive(page, state);
        } else if (ch >= 'd' && ch <= 'g') {
            uint32_t pair = (uint32_t)(ch - 'd');
            state->clock = (pair >> 1) & 1u;
            state->swdio = pair & 1u;
            drive(page, state);
        } else if (ch == 'c') {
            if (used == output_capacity) {
                (void)plasma_rbb_close(page, state);
                return PLASMA_BAD_BUFFER;
            }
            ordered_barrier();
            output[used++] = (load_word(page, 3, state) & 1u) ? '1' : '0';
        } else if (ch == 'r' || ch == 'B' || ch == 'b') {
            /* Only reset-deasserted and ignored LED; no NRST/JTAG. */
        } else {
            (void)plasma_rbb_close(page, state);
            return PLASMA_BAD_COMMAND;
        }
    }
    *output_len = used;
    return PLASMA_OK;
}

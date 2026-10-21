/* PLASMA ARMv7-A ordering primitive candidate.
 *
 * Build on a pinned ARMv7 hard-float cross-toolchain (GitHub-hosted A1):
 *   cc -O2 -fPIC -shared -o libplasma_mmio_barrier.so armv7_mmio_barrier.c
 *
 * DMB SY orders prior explicit MMIO stores before a subsequent COMMAND
 * store on the same processing element. It DOES NOT prove Linux mapping
 * attributes, cacheability, physical AXI completion or safe FPGA reload.
 * This source is NOT a qualified deployed library or HIL acceptance.
 */
#if !defined(__arm__) || defined(__aarch64__) || \
    !defined(__ARM_ARCH_7A__)
#error "PLASMA mmio barrier requires qualified ARMv7-A compiler target"
#endif

__attribute__((visibility("default")))
void plasma_mmio_dmb_sy(void)
{
    __asm__ __volatile__("dmb sy" ::: "memory");
}

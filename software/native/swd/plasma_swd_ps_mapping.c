/* SPDX-License-Identifier: GPL-2.0-or-later
 * No privileged device opener or hidden FPGA admission. Provides the
 * mmap/munmap lifecycle for one pre-authorized ABI-v5 Site using native C.
 * Host-only regular-file simulation is behind PLASMA_SWD_HOST_TEST only.
 */
#define _GNU_SOURCE
#include "plasma_swd_ps_mapping.h"
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

int plasma_swd_ps_mapping_attach(
    struct plasma_swd_ps_mapping *m, int fd,
    const struct plasma_swd_owner_lock *owner,
    unsigned int site_id, uint64_t generation,
    void *authority_ctx,
    int (*authorize)(void *, unsigned int, uint64_t),
    void (*revoke_all)(void *))
{
    if (!m || m->active || m->mapped || fd < 0 ||
        !plasma_swd_owner_lock_valid(owner) ||
        owner->site_id != site_id ||
        (site_id != 1u && site_id != 2u) || generation == 0 ||
        !authorize || !revoke_all)
        return PLASMA_SWD_BAD_ARG;

    /* Owned FD must be read/write and close-on-exec. O_SYNC is required
     * for the production /dev/mem path, matching existing LinuxMMIO.
     */
    const int flags = fcntl(fd, F_GETFL);
    const int fdflags = fcntl(fd, F_GETFD);
    if (flags < 0 || fdflags < 0 ||
        (flags & O_ACCMODE) != O_RDWR ||
        !(fdflags & FD_CLOEXEC))
        return PLASMA_SWD_NOT_READY;
#ifndef PLASMA_SWD_HOST_TEST
    if ((flags & O_SYNC) != O_SYNC)
        return PLASMA_SWD_NOT_READY;
#endif
    struct stat st;
    if (fstat(fd, &st) != 0)
        return PLASMA_SWD_NOT_READY;
#ifdef PLASMA_SWD_HOST_TEST
    /* Host tests may only map a regular synthetic file, never devices. */
    if (!S_ISREG(st.st_mode))
        return PLASMA_SWD_NOT_READY;
#else
    /* Linux /dev/mem is the character device major=1, minor=1.
     * This is merely an FD type check, NOT Root/Image attestation.
     * Other backends need a reviewed, explicit future Gate change.
     */
    if (!S_ISCHR(st.st_mode) || major(st.st_rdev) != 1u ||
        minor(st.st_rdev) != 1u)
        return PLASMA_SWD_NOT_READY;
#endif
    const uint32_t phys = site_id == 1u
        ? PLASMA_SWD_SITE1_BASE : PLASMA_SWD_SITE2_BASE;
#ifdef PLASMA_SWD_HOST_TEST
    if (st.st_size < (off_t)phys ||
        (uint64_t)st.st_size - (uint64_t)phys < PLASMA_SWD_NATIVE_PAGE_BYTES)
        return PLASMA_SWD_NOT_READY;
#endif

    /* This callback must obtain live protected Root/Boot/Image/voltage
     * facts from the authorized PS owner. A passed callback in a Host
     * test supplies NO such evidence for real hardware.
     */
    if (authorize(authority_ctx, site_id, generation) != 0)
        return PLASMA_SWD_NOT_READY;

    void *page = mmap(NULL, PLASMA_SWD_NATIVE_PAGE_BYTES,
                      PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)phys);
    if (page == MAP_FAILED)
        return PLASMA_SWD_NOT_READY;
    const int status = plasma_swd_native_words_init(
        &m->native, (volatile uint32_t *)page,
        PLASMA_SWD_NATIVE_PAGE_BYTES, owner, site_id,
        generation, authority_ctx, authorize, revoke_all);
    if (status != PLASMA_SWD_OK) {
        (void)munmap(page, PLASMA_SWD_NATIVE_PAGE_BYTES);
        return status;
    }
    /* Retest after mmap: do not expose a pointer after a revoked lease. */
    if (plasma_swd_native_words_ready(&m->native) != PLASMA_SWD_OK) {
        plasma_swd_native_words_retire(&m->native);
        (void)munmap(page, PLASMA_SWD_NATIVE_PAGE_BYTES);
        return PLASMA_SWD_NOT_READY;
    }
    m->mapped = page;
    m->mapped_bytes = PLASMA_SWD_NATIVE_PAGE_BYTES;
    m->pid = getpid();
    m->active = true;
    return PLASMA_SWD_OK;
}

void plasma_swd_ps_mapping_detach(struct plasma_swd_ps_mapping *m)
{
    if (!m || !m->active)
        return;
    /* Do not replay, disable clocks or access MMIO during cleanup.
     * Caller must unbind FIFO before releasing mapping/owner lock.
     */
    plasma_swd_native_words_retire(&m->native);
    if (m->mapped && m->pid == getpid())
        (void)munmap(m->mapped, m->mapped_bytes);
    m->mapped = NULL;
    m->mapped_bytes = 0;
    m->pid = 0;
    m->active = false;
}

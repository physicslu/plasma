/* SPDX-License-Identifier: GPL-2.0-or-later
 * Cooperative cross-process advisory lock, matching Python LinuxMMIO.open().
 * No open of /dev/mem, AXI access, Site admission, or extra supervisor.
 */
#define _GNU_SOURCE
#include "plasma_swd_owner_lock.h"

#include <errno.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>

int plasma_swd_owner_lock_acquire(struct plasma_swd_owner_lock *owner,
                                  const char *absolute_path)
{
    if (!owner || !absolute_path || absolute_path[0] != '/' ||
        owner->acquired)
        return -1;
#ifndef PLASMA_SWD_HOST_TEST
    /* Production must use the SAME lock inode/path as Python LinuxMMIO.
     * Arbitrary alternate paths would defeat cross-process exclusion. */
    if (strcmp(absolute_path, PLASMA_SWD_MMIO_OWNER_LOCK) != 0)
        return -1;
#endif
    /* LinuxMMIO uses O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW, mode 0600
     * and flock(LOCK_EX|LOCK_NB) on the EXACT same lock file.
     */
    int fd = open(absolute_path, O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0)
        return -1;
    struct stat st;
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode)) {
        close(fd);
        return -1;
    }
    if (flock(fd, LOCK_EX | LOCK_NB) != 0) {
        const int err = errno;
        close(fd);
        errno = err;
        return -1;
    }
    if (owner->epoch == UINT64_MAX) {
        (void)flock(fd, LOCK_UN);
        close(fd);
        return -1;
    }
    ++owner->epoch;
    owner->site_id = 0;
    owner->site_fd = -1;
    owner->fd = fd;
    owner->owner_pid = getpid();
    owner->acquired = true;
    return 0;
}

int plasma_swd_owner_lock_acquire_site(struct plasma_swd_owner_lock *owner,
                                       const char *ppu_lock_path,
                                       unsigned int site_id)
{
    if (!owner || !ppu_lock_path || ppu_lock_path[0] != '/' ||
        owner->acquired || (site_id != 1u && site_id != 2u))
        return -1;
#ifndef PLASMA_SWD_HOST_TEST
    if (strcmp(ppu_lock_path, PLASMA_SWD_MMIO_OWNER_LOCK) != 0)
        return -1;
#endif
    if (owner->epoch == UINT64_MAX)
        return -1;
    char site_path[512];
    int n = snprintf(site_path, sizeof(site_path), "%s.site-%u",
                     ppu_lock_path, site_id);
    if (n < 1 || (size_t)n >= sizeof(site_path))
        return -1;
    int fence = open(ppu_lock_path, O_CREAT | O_RDWR | O_CLOEXEC |
                    O_NOFOLLOW, 0600);
    if (fence < 0)
        return -1;
    struct stat st;
    if (fstat(fence, &st) != 0 || !S_ISREG(st.st_mode) || st.st_nlink != 1 ||
        flock(fence, LOCK_SH | LOCK_NB) != 0) {
        close(fence);
        return -1;
    }
    int site = open(site_path, O_CREAT | O_RDWR | O_CLOEXEC |
                    O_NOFOLLOW, 0600);
    if (site < 0) {
        close(fence);
        return -1;
    }
    if (fstat(site, &st) != 0 || !S_ISREG(st.st_mode) || st.st_nlink != 1 ||
        flock(site, LOCK_EX | LOCK_NB) != 0) {
        close(site);
        close(fence);
        return -1;
    }
    ++owner->epoch;
    owner->fd = fence;
    owner->site_fd = site;
    owner->site_id = site_id;
    owner->owner_pid = getpid();
    owner->acquired = true;
    return 0;
}

bool plasma_swd_owner_lock_valid(const struct plasma_swd_owner_lock *owner)
{
    return owner && owner->acquired && owner->fd >= 0 &&
           owner->epoch != 0 &&
           (owner->site_id == 0u || (owner->site_id <= 2u &&
                                     owner->site_fd >= 0)) &&
           owner->owner_pid == getpid();
}

void plasma_swd_owner_lock_release(struct plasma_swd_owner_lock *owner)
{
    if (!owner || !owner->acquired)
        return;
    /* A fork child must never unlock a lock owned by the parent.
     * The child closes only its duplicated file descriptor. */
    if (owner->site_id != 0u && owner->site_fd >= 0) {
        if (owner->owner_pid == getpid())
            (void)flock(owner->site_fd, LOCK_UN);
        (void)close(owner->site_fd);
    }
    if (owner->owner_pid == getpid())
        (void)flock(owner->fd, LOCK_UN);
    if (owner->fd >= 0)
        (void)close(owner->fd);
    owner->fd = -1;
    owner->site_fd = -1;
    owner->site_id = 0;
    owner->owner_pid = 0;
    owner->acquired = false;
}

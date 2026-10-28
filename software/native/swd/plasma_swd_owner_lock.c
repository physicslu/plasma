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
#include <unistd.h>

int plasma_swd_owner_lock_acquire(struct plasma_swd_owner_lock *owner,
                                  const char *absolute_path)
{
    if (!owner || !absolute_path || absolute_path[0] != '/' ||
        owner->acquired)
        return -1;
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
    owner->fd = fd;
    owner->owner_pid = getpid();
    owner->acquired = true;
    return 0;
}

bool plasma_swd_owner_lock_valid(const struct plasma_swd_owner_lock *owner)
{
    return owner && owner->acquired && owner->fd >= 0 &&
           owner->epoch != 0 &&
           owner->owner_pid == getpid();
}

void plasma_swd_owner_lock_release(struct plasma_swd_owner_lock *owner)
{
    if (!owner || !owner->acquired)
        return;
    /* A fork child must never unlock a lock owned by the parent.
     * The child closes only its duplicated file descriptor. */
    if (owner->owner_pid == getpid())
        (void)flock(owner->fd, LOCK_UN);
    if (owner->fd >= 0)
        (void)close(owner->fd);
    owner->fd = -1;
    owner->owner_pid = 0;
    owner->acquired = false;
}

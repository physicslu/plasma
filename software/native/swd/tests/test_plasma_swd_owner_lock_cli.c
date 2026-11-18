/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only subprocess helper for LinuxMMIO/C flock compatibility tests.
 * Holds only a temporary test file, never /dev/mem or a real Site.
 */
#include "../plasma_swd_owner_lock.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc != 3 && argc != 4)
        return 2;
    const bool site_mode = argc == 4;
    if (site_mode && (strcmp(argv[3], "1") && strcmp(argv[3], "2")))
        return 2;
    if (strcmp(argv[1], "hold") && strcmp(argv[1], "try"))
        return 2;
    struct plasma_swd_owner_lock lock = {.fd = -1};
    int rc = site_mode
        ? plasma_swd_owner_lock_acquire_site(&lock, argv[2],
                                           (unsigned int)(argv[3][0] - '0'))
        : plasma_swd_owner_lock_acquire(&lock, argv[2]);
    if (rc != 0) {
        puts("LOCK_BUSY_OR_DENIED");
        return 8;
    }
    if (!plasma_swd_owner_lock_valid(&lock))
        return 9;
    puts(strcmp(argv[1], "hold") ? "LOCK_ACQUIRED" : "LOCK_HELD");
    fflush(stdout);
    if (!strcmp(argv[1], "hold"))
        (void)getchar();
    plasma_swd_owner_lock_release(&lock);
    if (plasma_swd_owner_lock_valid(&lock))
        return 10;
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only subprocess helper for LinuxMMIO/C flock compatibility tests.
 * Holds only a temporary test file, never /dev/mem or a real Site.
 */
#include "../plasma_swd_owner_lock.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc != 3 || (strcmp(argv[1], "hold") && strcmp(argv[1], "try")))
        return 2;
    struct plasma_swd_owner_lock lock = {.fd = -1};
    if (plasma_swd_owner_lock_acquire(&lock, argv[2]) != 0) {
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

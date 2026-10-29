/* Host-only fake-authority test. NO device / Root / OpenOCD / DUT. */
#include "plasma_swd_recovery_gate.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

struct fake_authority {
    unsigned int site;
    uint64_t epoch;
    uint64_t generation;
    int intent;
    int live_owner;
    int verified;
    int checks;
    int pushes;
    int fail_push;
};

static int begin(void *ctx, unsigned int site_id, uint64_t epoch,
                 const char *job_id, uint64_t *generation)
{
    struct fake_authority *a = ctx;
    if (!a || site_id != a->site || epoch != a->epoch || !a->live_owner ||
        !a->verified || !job_id || !*job_id || a->intent)
        return -1;
    /* Fake durable intent; real trusted PS-local authority is NOT available. */
    a->intent = 1;
    *generation = a->generation;
    return 0;
}

static int check(void *ctx, unsigned int site_id,
                 uint64_t epoch, uint64_t generation)
{
    struct fake_authority *a = ctx;
    if (!a || site_id != a->site || epoch != a->epoch ||
        generation != a->generation || !a->intent ||
        !a->live_owner || !a->verified)
        return -1;
    a->checks++;
    return 0;
}

static int fake_push(void *ctx)
{
    struct fake_authority *a = ctx;
    assert(a->intent); /* No SWD PUSH callback before durable-intent claim. */
    a->pushes++;
    return a->fail_push ? -1 : 0;
}

static struct plasma_swd_recovery_authority callbacks(
    struct fake_authority *a)
{
    struct plasma_swd_recovery_authority cb = {a, begin, check};
    return cb;
}

int main(void)
{
    struct plasma_swd_recovery_gate g = {0};
    struct fake_authority a = {1u, 11u, 1u, 0, 1, 1, 0, 0, 0};
    struct plasma_swd_recovery_authority cb = callbacks(&a);

    /* Without trusted begin(), all synthetic SWD PUSH attempts are denied. */
    assert(plasma_swd_recovery_gate_push(&g, 1u, 11u,
                                         fake_push, &a) != 0);
    assert(a.pushes == 0);
    assert(plasma_swd_recovery_gate_begin(&g, NULL, 1u, 11u, "job") != 0);
    assert(plasma_swd_recovery_gate_begin(&g, &cb, 3u, 11u, "job") != 0);
    assert(plasma_swd_recovery_gate_begin(&g, &cb, 1u, 0, "job") != 0);
    assert(!a.intent);

    assert(plasma_swd_recovery_gate_begin(&g, &cb, 1u, 11u,
                                           "job-1") == PLASMA_RECOVERY_OK);
    assert(a.intent == 1);
    assert(a.checks == 1);
    /* Multiple PUSHes from the SAME live Site Owner are permitted after
     * one fake durable intent. There is no auto-READY between commands.
     */
    assert(plasma_swd_recovery_gate_push(&g, 1u, 11u,
                                         fake_push, &a) == PLASMA_RECOVERY_OK);
    assert(plasma_swd_recovery_gate_push(&g, 1u, 11u,
                                         fake_push, &a) == PLASMA_RECOVERY_OK);
    assert(a.pushes == 2 && a.checks == 3);
    assert(plasma_swd_recovery_gate_push(&g, 2u, 11u,
                                         fake_push, &a) != 0);
    assert(a.pushes == 2);
    assert(plasma_swd_recovery_gate_push(&g, 1u, 11u,
                                         fake_push, &a) != 0);
    assert(a.pushes == 2);

    /* A new process/lock epoch cannot inherit permission: even after retire,
     * fake durable intent is still present. No implicit re-admission.
     */
    plasma_swd_recovery_gate_retire(&g);
    assert(plasma_swd_recovery_gate_begin(&g, &cb, 1u, 11u,
                                           "job-retry") != 0);
    assert(a.pushes == 2);

    /* External authority revokes a live Owner immediately. */
    struct fake_authority b = {2u, 99u, 2u, 0, 1, 1, 0, 0, 0};
    struct plasma_swd_recovery_authority cb2 = callbacks(&b);
    assert(plasma_swd_recovery_gate_begin(&g, &cb2, 2u, 99u,
                                           "site2") == PLASMA_RECOVERY_OK);
    b.live_owner = 0;
    assert(plasma_swd_recovery_gate_push(&g, 2u, 99u,
                                         fake_push, &b) != 0);
    assert(b.pushes == 0 && b.intent == 1);

    /* Synthetic error after possible target side effect always poisons. */
    struct fake_authority c = {1u, 50u, 3u, 0, 1, 1, 0, 0, 1};
    struct plasma_swd_recovery_authority cb3 = callbacks(&c);
    assert(plasma_swd_recovery_gate_begin(&g, &cb3, 1u, 50u,
                                           "unknown-completion") == PLASMA_RECOVERY_OK);
    assert(plasma_swd_recovery_gate_push(&g, 1u, 50u,
                                         fake_push, &c) == PLASMA_RECOVERY_UNCERTAIN);
    assert(plasma_swd_recovery_gate_push(&g, 1u, 50u,
                                         fake_push, &c) != 0);
    assert(c.pushes == 1);

    /* A forked child cannot inherit its parent's in-process execution gate.
     * The child may carry copied memory, but not the original process PID.
     */
    struct fake_authority d = {2u, 60u, 4u, 0, 1, 1, 0, 0, 0};
    struct plasma_swd_recovery_authority cb4 = callbacks(&d);
    assert(plasma_swd_recovery_gate_begin(&g, &cb4, 2u, 60u,
                                           "fork") == PLASMA_RECOVERY_OK);
    pid_t pid = fork();
    assert(pid >= 0);
    if (pid == 0) {
        int rc = plasma_swd_recovery_gate_push(&g, 2u, 60u,
                                                fake_push, &d);
        _exit(rc == PLASMA_RECOVERY_DENIED && d.pushes == 0 ? 0 : 1);
    }
    int status = -1;
    assert(waitpid(pid, &status, 0) == pid);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    assert(plasma_swd_recovery_gate_push(&g, 2u, 60u,
                                         fake_push, &d) == PLASMA_RECOVERY_OK);
    assert(d.pushes == 1);

    puts("PLASMA_SWD_RECOVERY_GATE_HOST_ONLY_PASS");
    return 0;
}

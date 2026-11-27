# Pre-Start Time Synchronization v1

This is a best-effort observation and correction before the first Job of each
PPU in a Manager Batch, including a managed Single Run. It is not Programming
Admission. `SYNCED` and `CORRECTED` are time-sync outcomes, never Flash PASS.

## Existing service audit

The PPU installer does not install or configure chrony, systemd-timesyncd, or
ntpd. The active service, source configuration, chronyc socket permission, and
real Z2 clock state are **NOT_VERIFIED**. No SWPC or Console timestamp is a
source. The implementation uses only a locally configured, synchronised
chronyd as its time reference. If chronyc is absent, it reports `UNSUPPORTED`;
if the daemon is unavailable, it reports `UNAVAILABLE`. A PPU without a
trusted configured source reports `UNTRUSTED_SOURCE`. Installing or configuring
an NTP service on an actual PPU is outside this Host-only Gate 1.

Chronyd is the protected local Linux service that changes CLOCK_REALTIME.
The unprivileged `plasma-server` process invokes the fixed `chronyc -n tracking`
and, only above the configured offset threshold, `chronyc -n makestep` through
chronyd's existing Unix control socket. A PPU whose service account cannot
issue `makestep` reports `FAILED` with `CHRONYC_PERMISSION_DENIED`; this change
does not modify sudoers, service users, or OS capabilities. It accepts no
Console time, arbitrary timestamp, process argument, or shell command. The
immediate, parameterless `makestep` consumes the current remaining chronyd
correction; the scheduled `makestep threshold updates` form is never used.
No NTP daemon is stopped, paused or reconfigured during a Batch.

Chrony `tracking` must report normal leap status, a nonlocal reference,
stratum 1–15, parseable System time, and root dispersion within the threshold.
System time is chronyd's remaining CLOCK_REALTIME correction relative to its
configured source, not a measured SWPC↔PPU network offset. Root dispersion is
recorded as an uncertainty bound. `CORRECTED` requires a second trustworthy
tracking observation within the threshold after `makestep` returns; a command
exit code alone cannot establish it. `SYNCED` skips `makestep`. A corrected
PPU UTC observation can move relative to previously written Manager UTC
timestamps; durations, Reservation TTL and Job timeouts retain their existing
monotonic clocks. No Root Guard, SAFE_OFF, recovery or unknown-outcome policy
is changed.

## Trigger and exclusion

The Manager journals acceptance before any PPU call. The canonical Batch
activates Resources before Reservation, then acquires each PPU's existing
Resource Reservation. Its first Site lane makes one PPU-wide call before any Job;
other lanes on that PPU share its result. Each PPU runs independently. Repeat,
Retry, Continue, Job polling, and Direct/Unmanaged PPU Job APIs make no
additional time-sync call. Direct/Unmanaged callers are not promised automatic
time sync. A warning cannot change a Job or Batch outcome.

The PPU SiteManager holds its existing `_execution_lock` across the safety
check and bounded chronyc calls. It refuses correction when there is another
owner's Reservation, any Job lease or unfinished Job, Runtime Quiesce/B3, or
an unverified Root Site Worker state. A Batch call must present its own active
Reservation owner and token, with no reserved Job yet. In production, the
existing Site Worker control socket reports live Sessions, persisted seals,
Root Admission Record sites, and adapter readiness; any nonempty or unreadable
result causes `SKIPPED_BUSY`. This is one admission lock, not a second lock
manager. External hardware tools outside the PPU Site Worker remain the
operator's separate ownership responsibility.

The Gateway exposes only `POST /api/pre-start-time-sync` with `owner_id`,
optional Reservation `token`, `threshold_ms` and `budget_ms`. It uses existing
Controller write admission (`site.job.submit`) and Protocol v3.3 to reach the
PPU. The Manager is its normal caller; the Browser does not call it. Threshold
defaults to 100 ms (`PLASMA_PRESTART_TIME_SYNC_THRESHOLD_MS`, 1–1000 ms),
total command budget to 1000 ms (`PLASMA_PRESTART_TIME_SYNC_BUDGET_MS`,
100–5000 ms). Each subprocess has the remaining monotonic deadline; a timed
out subprocess is terminated, and the result is a warning. No `burst` or
future-step command is issued that could intentionally step during a Batch.

The existing Batch journal records the status, PPU ID, source/service,
measured offsets when available, elapsed time, adjustment flag, warning code,
UTC observation time and dispersion. EMode and PMode show one log line per PPU
through their existing Batch polling UI. No new Dashboard or settings page is
introduced.

## Evidence boundary

Host-only tests replace the chronyc subprocess runner and never invoke a real
clock write. They prove software sequencing and warning behavior, not that a
particular Z2 has chrony, a trusted upstream, correction permission, a measured
offset, or sub-200 ms real network latency. Those remain **NOT_VERIFIED** until
a separately authorised PPU deployment and physical observation after Gate 2.

#!/usr/bin/env python3
"""Deterministic Path 2 two-Site programming loading benchmark (no install)."""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import time


def stat_parse(raw):
    # comm can contain spaces and ')' characters; fields after final ')' are fixed.
    end = raw.rindex(')')
    fields = raw[end + 2:].split()
    return dict(pid=int(raw[:raw.index('(')].strip()), ppid=int(fields[1]),
                ticks=int(fields[11]) + int(fields[12]), starttime=int(fields[19]))


def memory(raw):
    return {line.split(':')[0]: int(line.split()[1]) for line in raw.splitlines()
            if line.startswith(('VmRSS:', 'MemTotal:', 'MemAvailable:'))}


def site_parse(raw):
    argv = raw.decode('utf-8', 'replace').split('\0')
    commands = [argv[i + 1].strip() for i, a in enumerate(argv[:-1]) if a == '-c']
    sites = [int(c[-1]) for c in commands if c in ('plasma_swd site 1', 'plasma_swd site 2')]
    if 'adapter driver plasma_swd' not in commands or len(sites) != 1:
        return None
    return sites[0]


def host_cpu(raw):
    values = list(map(int, raw.splitlines()[0].split()[1:9]))  # excludes guest double count
    return sum(values), values[3] + values[4]


def cpu_percent(old, new, dt, hz):
    if old is None or dt <= 0 or new['starttime'] != old['starttime']:
        return None
    delta = new['ticks'] - old['ticks']
    return 100 * delta / hz / dt if delta >= 0 else None


def transitions(previous, current):
    return ([dict(event='FIRST_OBSERVED', pid=k[0], starttime=k[1]) for k in current.keys() - previous.keys()]
            + [dict(event='NO_LONGER_OBSERVED', pid=k[0], starttime=k[1]) for k in previous.keys() - current.keys()])


def dual(processes):
    return any(a['site'] == 1 and b['site'] == 2 and a['pid'] != b['pid']
               for a in processes for b in processes)


def scan(root):
    processes, errors = {}, []
    prefix = str(root) + '/'
    for name in os.listdir(root):
        if not name.isdecimal():
            continue
        try:
            # A raw bounded read avoids Path/TextIO allocation for every unrelated PID.
            with open(prefix + name + '/comm', 'rb', buffering=0) as f:
                if f.read(32).strip() != b'openocd':
                    continue
            entry = root / name
            first = stat_parse((entry / 'stat').read_text())
            site = site_parse((entry / 'cmdline').read_bytes())
            rss = memory((entry / 'status').read_text()).get('VmRSS')
            last = stat_parse((entry / 'stat').read_text())
            if first['starttime'] != last['starttime']:
                errors.append('PID_REUSED_DURING_READ')
                continue
            last.update(site=site, rss_kib=rss, command=(
                'openocd -c "adapter driver plasma_swd" -c "plasma_swd site %s"' % site
                if site else 'openocd [UNVALIDATED_ARGUMENTS_REDACTED]'))
            processes[(last['pid'], last['starttime'])] = last
        except FileNotFoundError:
            continue  # process disappeared during enumeration
        except (PermissionError, ValueError, IndexError, OSError) as exc:
            errors.append(type(exc).__name__)
    # Revalidate every identity at the end of the frame to reject processes
    # which exited or were replaced while the other Site was being sampled.
    for key in list(processes):
        try:
            check = stat_parse((root / str(key[0]) / 'stat').read_text())
            if check['starttime'] != key[1]:
                raise ValueError('reused')
        except (OSError, ValueError, IndexError):
            del processes[key]
            errors.append('PROCESS_CHANGED_DURING_FRAME')
    return processes, errors


def sample(args, root=Path('/proc'), stop=None):
    stop = stop or threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda signum, frame: stop.set())
    hz = os.sysconf('SC_CLK_TCK')
    started = time.monotonic()
    own_start = time.process_time()
    previous, previous_t, previous_cpu = {}, None, None
    frames, events, peak = [], [], {}
    overlap_s, previous_dual, dual_count = 0., False, 0
    csv_path, json_path = Path(args.output + '.csv'), Path(args.output + '.json')
    fields = ['frame', 'utc', 'monotonic_s', 'scan_duration_s', 'site', 'observation', 'pid', 'ppid',
              'starttime', 'cpu_pct_one_core', 'rss_kib', 'host_cpu_pct_all_cores',
              'mem_available_kib', 'mem_total_kib', 'observer_cpu_pct_one_core', 'observer_rss_kib', 'missed_samples']
    with csv_path.open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        deadline = started + args.duration
        due = started
        while time.monotonic() < deadline and not stop.is_set():
            t = time.monotonic()
            utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            current, errors = scan(root)
            cpu = host_cpu((root / 'stat').read_text())
            mem = memory((root / 'meminfo').read_text())
            own = stat_parse((root / 'self/stat').read_text())
            own_rss = memory((root / 'self/status').read_text()).get('VmRSS')
            dt = t - previous_t if previous_t is not None else 0
            host = None
            if previous_cpu and cpu[0] > previous_cpu[0]:
                host = 100 * (1 - (cpu[1] - previous_cpu[1]) / (cpu[0] - previous_cpu[0]))
            own_pct = cpu_percent(previous.get('self'), own, dt, hz)
            old_processes = {k: v for k, v in previous.items() if k != 'self'}
            ev = transitions(old_processes, current)
            events.extend(dict(e, utc=utc, monotonic_s=t) for e in ev)
            procs = []
            for key, proc in current.items():
                proc['cpu_pct_one_core'] = cpu_percent(previous.get(key), proc, dt, hz)
                procs.append(proc)
                identity = '%s:%s' % key
                peaks = peak.setdefault(identity, dict(pid=key[0], starttime=key[1], ppid=proc['ppid'], site=proc['site'], cpu_pct_one_core=None, rss_kib=None))
                for metric in ('cpu_pct_one_core', 'rss_kib'):
                    value = proc[metric]
                    if value is not None:
                        peaks[metric] = max(value, peaks[metric] if peaks[metric] is not None else value)
            concurrent = dual(procs) and not errors
            dual_count += int(concurrent)
            if concurrent and previous_dual:
                # Sample-to-sample estimate only, not continuous lifetime proof.
                overlap_s += dt
            previous_dual = concurrent
            base = dict(frame=len(frames), utc=utc, monotonic_s=t, scan_duration_s=time.monotonic()-t,
                        host_cpu_pct_all_cores=host, mem_available_kib=mem.get('MemAvailable'),
                        mem_total_kib=mem.get('MemTotal'), observer_cpu_pct_one_core=own_pct,
                        observer_rss_kib=own_rss)
            frame = dict(base, processes=procs, errors=errors, dual_pid_sample=concurrent)
            frame['missed_samples'] = max(0, int((t - due) / args.interval))
            base['missed_samples'] = frame['missed_samples']
            frames.append(frame)
            # Durable READY follows a real sample, never merely process creation.
            atomic_json(Path(args.output + '.latest.json'), frame)
            if len(frames) == 1:
                atomic_json(Path(args.output + '.ready.json'), frame)
            for site in (1, 2):
                selected = [p for p in procs if p['site'] == site]
                for p in selected or [None]:
                    row = dict(base, site=site, observation=('OBSERVED' if p else 'MISSING' if errors else 'NOT_OBSERVED'))
                    if p:
                        row.update({k: p[k] for k in ('pid','ppid','starttime','cpu_pct_one_core','rss_kib')})
                    writer.writerow(row)
            previous, previous_t, previous_cpu = dict(current, self=own), t, cpu
            due += (frame['missed_samples'] + 1) * args.interval
            stop.wait(max(0, min(due, deadline) - time.monotonic()))
    elapsed = time.monotonic() - started
    report = dict(schema='plasma.z2.proc-observer.v1', hostname=os.uname().nodename,
                  uid=os.geteuid(), boot_id=(root / 'sys/kernel/random/boot_id').read_text().strip(),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  hz=hz, interval_s=args.interval, requested_duration_s=args.duration,
                  elapsed_s=elapsed, termination='SIGNAL' if stop.is_set() else 'DURATION',
                  cpu_units='PID/observer:100%=one core;host:100%=all cores; RSS/memory:KiB',
                  cpu_accounting='PID/observer sampled CPU = user+system ticks; observer average = process_time user+system; host busy includes user/nice/system/irq/softirq/steal, excludes idle+iowait',
                  observer_average_cpu_pct_one_core=100*(time.process_time()-own_start)/elapsed,
                  observer_peak_rss_kib=max((f['observer_rss_kib'] or 0 for f in frames), default=0),
                  concurrency='CONCURRENCY_CONFIRMED' if dual_count else 'NOT_OBSERVED',
                  dual_pid_samples=dual_count, sampled_overlap_estimate_s=overlap_s,
                  missed_samples=sum(f['missed_samples'] for f in frames),
                  overlap_basis='sum of intervals bounded by dual-positive frames; gaps can hide transitions',
                  job_correlation='NOT_VERIFIED; no Batch/Job identity inferred',
                  lifecycle_basis='first/last observed, not exact process birth/death',
                  peaks=list(peak.values()), events=events, frames=frames)
    with json_path.open('x') as f:
        json.dump(report, f, indent=2, allow_nan=False)
    with Path(args.output + '.sha256').open('x') as f:
        for path in (csv_path,json_path):
            f.write(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
    print(json.dumps({k: report[k] for k in ('concurrency','elapsed_s','dual_pid_samples','observer_average_cpu_pct_one_core','observer_peak_rss_kib','termination')}), flush=True)
    return report


# Controller imports remain standard-library only on SWPC and Z2.
import base64
import http.client
import ipaddress
import math
import re
import stat
import subprocess
import sys
import zlib
from urllib.parse import urlsplit, quote

SCHEMA = 'plasma.programming.loading-benchmark.v1'
ROOT = Path(__file__).resolve().parents[1]
TARGET = 'STM32F103C8T6'
OPERATIONS = ['erase', 'program', 'verify']
TERMINAL = {'PASS', 'FAIL', 'PARTIAL', 'BLOCKED', 'OUTCOME_UNKNOWN', 'CANCELLED'}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
# Trusted Dispatcher creates this protected, never-updatable ref once per
# Work Order digest BEFORE execution (cross-Run exactly-once; PR-H).
CLAIM_PREFIX = 'refs/heads/plasma-engineering-claims/981/p2hw-'
VOID_TOKEN = 'VOID_UNSTARTED_START'
ID = re.compile(r'[0-9a-f]{32}\Z')


class Blocked(RuntimeError):
    """Only fixed diagnostic codes may cross the evidence boundary."""


def require(condition, code):
    if not condition:
        raise Blocked(code)


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.writing')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, allow_nan=False, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def stats(values):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    if not values:
        return {'n': 0, 'mean': None, 'p95': None, 'peak': None}
    return dict(n=len(values), mean=sum(values)/len(values),
                p95=values[math.ceil(.95*len(values))-1], peak=values[-1])


def comparison(frames, submitted, terminal, recovery_start, interval):
    """Phase boundaries are Z2 monotonic times; never compare host monotonic clocks."""
    phases = {k: [] for k in ('idle', 'single_site', 'dual_site', 'batch_no_pid', 'recovery')}
    for f in frames:
        t = f['monotonic_s']
        if f['errors'] or any(p['site'] not in (1, 2) for p in f['processes']):
            continue
        sites = {p['site'] for p in f['processes']}
        if sites and (t < submitted or t >= recovery_start):
            continue  # Never relabel pre-submission/recovery activity as Batch load.
        phase = ('idle' if t < submitted and not sites else
                 'recovery' if t >= recovery_start and not sites else
                 'dual_site' if sites == {1, 2} else
                 'single_site' if len(sites) == 1 else 'batch_no_pid')
        phases[phase].append(f)
    result = {}
    for phase, selected in phases.items():
        duration = sum(b['monotonic_s']-a['monotonic_s'] for a,b in zip(selected,selected[1:])
                       if b['frame'] == a['frame']+1)
        cpu = stats(f['host_cpu_pct_all_cores'] for f in selected)
        ram = stats(f['mem_total_kib']-f['mem_available_kib'] for f in selected)
        result[phase] = dict(n=len(selected), duration_s=duration, cpu_pct=cpu,
                            ram_used_kib=ram, ram_used_pct=stats(
                                100*(1-f['mem_available_kib']/f['mem_total_kib']) for f in selected),
                            observer_cpu_one_core=stats(f['observer_cpu_pct_one_core'] for f in selected),
                            observer_rss_kib=stats(f['observer_rss_kib'] for f in selected),
                            quality=('NOT_OBSERVED' if not selected else 'INSUFFICIENT_SAMPLES'
                                     if cpu['n'] < 3 or duration < 2*interval else 'OBSERVED'),
                            cpu_headroom_pct=100-cpu['peak'] if cpu['peak'] is not None else None)
    idle = result['idle']
    for phase in result.values():
        for metric, label in (('cpu_pct', 'cpu_delta_pp'), ('ram_used_pct', 'ram_delta_pp')):
            phase[label] = {k: (phase[metric][k]-idle[metric][k]
                               if phase[metric][k] is not None and idle[metric][k] is not None else None)
                            for k in ('mean', 'p95', 'peak')}
    pids = {}
    for f in frames:
        for p in f['processes']:
            key = '%s:%s' % (p['pid'], p['starttime'])
            pids.setdefault(key, []).append((f,p))
    process_report = {}
    for key, entries in pids.items():
        process_report[key] = dict(pid=entries[0][1]['pid'], starttime=entries[0][1]['starttime'],
                                  site=entries[0][1]['site'], ppid=entries[0][1]['ppid'],
                                  first_utc=entries[0][0]['utc'], last_utc=entries[-1][0]['utc'],
                                  cpu_one_core=stats(p['cpu_pct_one_core'] for _,p in entries),
                                  rss_kib=stats(p['rss_kib'] for _,p in entries))
    overlap = 0.
    for a,b in zip(frames,frames[1:]):
        # The SAME two identities must bound the interval. PID reuse breaks it.
        identities = lambda f: {(p['pid'],p['starttime'],p['site']) for p in f['processes']}
        common = identities(a) & identities(b)
        dt = b['monotonic_s']-a['monotonic_s']
        if (submitted <= a['monotonic_s'] < b['monotonic_s'] < recovery_start
                and not a['errors'] and not b['errors']
                and {p[2] for p in common} == {1,2} and dt <= interval*1.5):
            overlap += dt
    max_gap = max((b['monotonic_s']-a['monotonic_s'] for a,b in zip(frames,frames[1:])),default=0)
    return dict(phases=result, pids=process_report, sampled_pid_overlap_s=overlap,
                overlap_status='OBSERVED' if overlap else 'NOT_OBSERVED',
                overlap_boundary_uncertainty_s=max_gap+max((f['scan_duration_s'] for f in frames),default=0),
                overlap_basis='sampled estimate; gaps may hide exits; no continuous lifetime proof',
                missed_samples=sum(f.get('missed_samples',0) for f in frames),
                batch_terminal_monotonic_s=terminal if math.isfinite(terminal) else None,
                historical_baseline='NON_COMPARABLE', scaling_to_eight_sites='NOT_RUN')


class HTTP:
    def __init__(self, manager):
        parsed = urlsplit(manager)
        require(parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')
                and parsed.port and not parsed.username and not parsed.password and not parsed.query
                and not parsed.fragment and parsed.path in ('','/'), 'MANAGER_ROUTE_INVALID')
        self.host, self.port = parsed.hostname, parsed.port

    def request(self, method, path, body=None):
        remaining = getattr(self,'deadline',time.monotonic()+10)-time.monotonic()
        require(remaining > 0,'BENCHMARK_TIMEOUT')
        limit = 30 if (method, path) == ('POST', '/api/programming/batches') else 10
        conn = http.client.HTTPConnection(self.host, self.port, timeout=min(limit,remaining))
        try:
            conn.request(method, path, body=json.dumps(body) if body is not None else None,
                         headers={'Content-Type':'application/json', 'Accept':'application/json'})
            res = conn.getresponse()
            raw = res.read(2*1024*1024+1)
            require(len(raw) <= 2*1024*1024, 'HTTP_EVIDENCE_TOO_LARGE')
            data = json.loads(raw)
            require(isinstance(data,dict) and res.status in (200,201,202) and data.get('ok') is True,
                    'HTTP_REQUEST_REJECTED')
            return data
        finally:
            conn.close()


def idle(status):
    ppu = status['ppu']
    require(ppu['ppu_id'] == 'z2-hil' and ppu['execution']['busy'] is False
            and ppu['execution']['active_job_count'] == 0
            and ppu['runtime_activation']['active'] is False, 'PPU_BUSY_OR_IDENTITY_MISMATCH')
    selected = [s for s in status['sites'] if s['site_id'] in (1,2)]
    require(sorted(s['site_id'] for s in selected) == [1,2], 'SITES_MISSING')
    require(all(s['enabled'] is True and s['interface'] == 'openocd' and s['state'] == 'idle'
                and s['current_job_id'] is None and s['queued_jobs'] == 0 for s in selected), 'SITES_BUSY_OR_DISABLED')


def check_plan(plan, cfg, site, image):
    binding, route = plan['job_binding'], plan['route']
    require(plan['activation_required'] is False and plan['fpga_load'] is False
            and plan['resource']['reuse'] is True, 'ACTIVATION_OR_LOAD_REQUIRED')
    require(binding['site_id'] == site and binding['icpn'] == TARGET
            and binding['ppu_id'] == 'z2-hil' and binding['operations'] == OPERATIONS
            and binding['profile'] == cfg['profile'] and route['route_id'] == cfg['route_id']
            and route['driver_abi'] == 'plasma_swd:5' and route['transport'] == 'fpga'
            and route['site_interface'] == 'openocd', 'TARGET_OR_ROUTE_MISMATCH')
    require(plan['image_asset']['sha256'] == cfg['image_sha256']
            and plan['image_asset']['size'] == len(image), 'IMAGE_MISMATCH')
    r = plan['resource']['ppu_reported']
    require(r['state'] == 'VERIFIED' and r['asset_set_sha256'] == cfg['asset_set_sha256']
            and r['generation'] == cfg['generation']
            and r['resource_set_sha256'] == cfg['resource_set_sha256']
            and binding['resource_set_sha256'] == cfg['resource_set_sha256'], 'ACTIVE_RESOURCE_MISMATCH')


def submit_once(client, body, journal, save):
    """A durable intent precedes POST. Even explicit rejection never retries.

    A lost response is reconciled read-only. A Start that is still admissible
    (ACCEPTANCE_PENDING) is voided: the Manager serializes void and admission,
    so either the Start can never be admitted (NOT_ACCEPTED) or the void is
    refused because the Batch exists and is then tracked. Never resent.
    """
    require(journal.get('batch_post_count',0) == 0, 'DUPLICATE_SUBMISSION_DENIED')
    journal.update(batch_post_count=1, outcome='OUTCOME_UNKNOWN', start_id=body['start_id'],
                   submission='UNKNOWN')
    save()
    start_path = '/api/programming/starts/'+body['start_id']
    try:
        response = client.request('POST','/api/programming/batches',body)
        batch = response['batch']
    except Exception:
        def reconcile(name):
            journal[name] = client.request('GET',start_path)
            save()
            rec = journal[name]['reconciliation']
            require(rec['start_id'] == body['start_id'], 'SUBMISSION_UNKNOWN_NO_RESEND')
            return rec
        rec = reconcile('reconciliation')
        if rec['state'] == 'ACCEPTANCE_PENDING':
            journal['void_post_count'] = 1;save()
            try:
                journal['void'] = client.request('POST',start_path+'/void',{'void':VOID_TOKEN})
                save()
            except Exception:
                pass  # Refused/lost void: only the read-only view decides.
            rec = reconcile('reconciliation_after_void')
        if rec['state'] == 'NOT_ACCEPTED':
            journal['submission'] = 'NOT_ACCEPTED';save()
            raise Blocked('SUBMISSION_NOT_ACCEPTED_NO_RESEND')
        require(rec['state'] in ('ACCEPTED_RUNNING','TERMINAL_CONFIRMED'), 'SUBMISSION_UNKNOWN_NO_RESEND')
        batch = rec['batch']
    require(ID.fullmatch(batch['batch_id']) and batch['start_id'] == body['start_id']
            and batch['targets'] == [{'ppu_alias':'z2','site_ids':[1,2]}], 'BATCH_IDENTITY_MISMATCH')
    journal['batch_id'] = batch['batch_id']
    journal['submission'] = 'ACCEPTED'
    save()
    return batch['batch_id']


def require_hardware_claim(report):
    """Fail closed before any IO unless the trusted cross-Run claim exists."""
    sha = report.get('work_order_sha256')
    require(isinstance(sha,str) and HEX64.fullmatch(sha)
            and os.environ.get('PLASMA_P2HW_CLAIM_REF') == CLAIM_PREFIX+sha,
            'HARDWARE_CLAIM_REQUIRED')
    report['hardware_claim_ref'] = CLAIM_PREFIX+sha


def site_result(job, site, cfg):
    """Per-Site physical result, recorded even when another Site failed."""
    try:
        return check_job(job, site, cfg)
    except (Blocked, KeyError, TypeError) as exc:
        receipt = ((job.get('result') or {}).get('details') or {}).get('programming') or {}
        return dict(job_id=job.get('job_id'), site_id=site, result='FAIL', state=job.get('state'),
                    safe_off=receipt.get('safe_off'), blocker=str(exc) if isinstance(exc,Blocked) else type(exc).__name__)


def trace(report):
    """Physical Batch result and Observer/benchmark result, separately traceable."""
    if not report['batch_post_count']:
        submission = 'NOT_SUBMITTED'
    else:
        submission = report.get('submission') or 'UNKNOWN'
    report['hardware_trace'] = dict(
        start_issuance=report.get('start_issuance','NOT_REQUESTED'), start_id=report.get('start_id'),
        submission=submission, batch_id=report.get('batch_id'),
        batch_outcome=report.get('batch_outcome') or report.get('cleanup_batch_outcome'),
        sites=report.get('site_results',[]), final_idle=report.get('final_idle'))
    c = report.get('comparison')
    if report.get('observer') is None:
        measured = 'NOT_STARTED'
    elif report.get('cleanup'):
        measured = 'FAILED'
    elif not c:
        measured = 'NO_BATCH_WINDOW'
    elif report.get('measurement_insufficient'):
        measured = 'INSUFFICIENT_SAMPLES'
    elif not c['sampled_pid_overlap_s']:
        measured = 'NOT_OBSERVED'
    else:
        measured = 'OBSERVED'
    report['measurement_trace'] = dict(observer_termination=report.get('observer_termination'),
        error=report.get('cleanup'), comparison=bool(c), measurement_outcome=measured)


def check_job(job, site, cfg):
    result = job['result']
    receipt = result['details']['programming']
    require(job['site_id'] == site and job['operation'] == 'programming' and job['state'] == 'success'
            and job['attempt'] == 1 and result['attempts'] == 1
            and receipt['site'] == site and receipt['operations'] == OPERATIONS
            and receipt['safe_off'] is True and receipt['openocd_rc'] == 0
            and receipt['steps']['verify']['readback_sha256'] == cfg['image_sha256']
            and result['image_sha256'] == cfg['image_sha256'], 'JOB_FAILURE_OR_READBACK_SAFE_OFF_MISMATCH')
    return dict(job_id=job['job_id'],site_id=site,result='PASS', safe_off=True,
                readback_sha256=receipt['steps']['verify']['readback_sha256'],bytes=result['image_size'],
                elapsed_ms=result['elapsed_ms'], reset_run='EXISTING_POST_PROGRAM_RESET_RUN_ACCEPTED_NOT_NO_RESET_QUALIFICATION')


class Remote:
    """Use the existing enrolled SSH transport; no new credential or privilege path."""
    def __init__(self):
        import plasma_wordport_program as enrolled
        self.helper = enrolled
        self.credentials, self.hosts = enrolled.z2_login_credentials(Path.home())
        require(ipaddress.ip_address(self.credentials['ssh_host']).is_private, 'ENROLLED_HOST_NOT_PRIVATE')

    def execute(self, code, timeout=30):
        remaining = getattr(self,'deadline',time.monotonic()+timeout)-time.monotonic()
        require(remaining > 0,'BENCHMARK_TIMEOUT')
        timeout = max(1,min(timeout,math.ceil(remaining)))
        rc, transcript = self.helper.password_ssh_z2(
            ['python3','-I','-c',code], self.credentials,self.hosts,timeout=timeout)
        require(rc == 0, 'ENROLLED_SSH_OPERATION_FAILED')
        hits = re.findall(r'(?m)^BENCH_JSON=(\{[^\r\n]*\})\s*$',transcript)
        require(len(hits) == 1, 'REMOTE_EVIDENCE_INVALID')
        return json.loads(hits[0])

    def inspect(self):
        # Reuse existing reviewed Root metadata/Engine/hash/boot observer.
        import plasma_site2_path2_preflight as preflight
        code = preflight.REMOTE + '''
import yaml
config=yaml.safe_load(P('/etc/plasma/ppu.yaml').read_text())
print('BENCH_JSON='+json.dumps({'metadata':result,'config':config,
 'seals':[p.name for p in P('/var/lib/plasma-site-worker/seals').glob('*')],
 'admissions':[p.name for p in P('/run/plasma-z2-swd05').glob('*admission*')]}))
'''
        return self.execute(code)

    def launch(self, cfg, args):
        source = Path(__file__).read_bytes()
        payload = base64.b64encode(zlib.compress(source)).decode()
        return self.execute('''
import base64,zlib,pathlib,subprocess,sys,json,os,pwd
P=pathlib.Path
r=P('/tmp')/('plasma-loading-'+__import__('uuid').uuid4().hex);r.mkdir(mode=0o700)
source=zlib.decompress(base64.b64decode(%r));p=r/'observer.py';p.write_bytes(source)
# The /proc sampler needs no root rights. Drop to the enrolled Z2 account.
account=pwd.getpwnam('xilinx');os.chown(r,account.pw_uid,account.pw_gid);os.chown(p,account.pw_uid,account.pw_gid)
log=(r/'observer.log').open('xb')
def demote():
 os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
child=subprocess.Popen([%r,'-I',str(p),'sample','--output',str(r/'samples'),
 '--interval',%r,'--duration',%r],stdin=subprocess.DEVNULL,stdout=log,stderr=log,
 start_new_session=True,preexec_fn=demote)
print('BENCH_JSON='+json.dumps({'pid':child.pid,'directory':str(r),'source_sha256':__import__('hashlib').sha256(source).hexdigest(),'starttime':int(P('/proc/%%d/stat'%%child.pid).read_text().rsplit(')',1)[1].split()[19])}))
''' % (payload,cfg['z2_python'],str(args.interval_ms/1000),str(args.timeout_sec)))

    def status(self, observer, stop=False):
        return self.execute('''
import pathlib,json,os,signal
P=pathlib.Path;r=P(%r);pid=%d
p=P('/proc')/str(pid)
if %r and p.exists():
 cmd=(p/'cmdline').read_bytes().split(b'\\0')
 assert str(r/'observer.py').encode() in cmd and int((p/'stat').read_text().rsplit(')',1)[1].split()[19]) == %d,'IDENTITY_CHANGED'
 os.kill(pid,signal.SIGTERM)
def read(name):
 p=r/name
 return json.loads(p.read_text()) if p.exists() else None
print('BENCH_JSON='+json.dumps({'ready':read('samples.ready.json'),'latest':read('samples.latest.json'),
 'finished':(r/'samples.json').exists(),'alive':p.exists()}))
''' % (observer['directory'],observer['pid'],stop,observer['starttime']))

    def remove(self, observer):
        return self.execute('''
import pathlib,json,hashlib
P=pathlib.Path;r=P(%r);p=P('/proc')/str(%d)
assert r.parent==P('/tmp') and r.name.startswith('plasma-loading-')
assert not p.exists() or (p/'stat').read_text().rsplit(')',1)[1].split()[0]=='Z'
assert hashlib.sha256((r/'observer.py').read_bytes()).hexdigest()==%r
allowed={'observer.py','observer.log','samples.json','samples.csv','samples.sha256','samples.latest.json','samples.ready.json'}
assert {p.name for p in r.iterdir()} <= allowed
for name in allowed:
 p=r/name
 if p.exists():p.unlink()
r.rmdir()
print('BENCH_JSON='+json.dumps({'ephemeral_removed':True}))
''' % (observer['directory'],observer['pid'],observer['source_sha256']))

    def collect(self, observer, output):
        # Chunked transfer stays below existing 128 KiB SSH transcript bound.
        collection_deadline = time.monotonic()+90
        for name in ('samples.json','samples.csv','samples.sha256'):
            offset = 0
            with (output/name).open('xb') as stream:
                while True:
                    require(time.monotonic() < collection_deadline, 'EVIDENCE_COLLECTION_TIMEOUT')
                    part = self.execute('''
import pathlib,json,base64
p=pathlib.Path(%r)/%r
with p.open('rb') as f:f.seek(%d);b=f.read(32768)
print('BENCH_JSON='+json.dumps({'bytes':base64.b64encode(b).decode()}))
''' % (observer['directory'],name,offset))
                    chunk = base64.b64decode(part['bytes'],validate=True)
                    stream.write(chunk);offset += len(chunk)
                    require(offset <= 64*1024*1024, 'REMOTE_ARTIFACT_LIMIT')
                    if len(chunk) < 32768:
                        break
        report = json.loads((output/'samples.json').read_text())
        require(report['uid'] > 0 and report['script_sha256'] == observer['source_sha256'], 'OBSERVER_SOURCE_MISMATCH')
        for line in (output/'samples.sha256').read_text().splitlines():
            expected,name = line.split('  ')
            require(name in ('samples.csv','samples.json') and digest((output/name).read_bytes()) == expected,
                    'OBSERVER_EVIDENCE_HASH_MISMATCH')
        return report


def authorization(argv):
    import plasma_development_dispatch as dispatch
    # A workflow re-run replays the same owner event with a fresh RUNNER_TEMP
    # and workspace, so no local claim survives it. Never resubmit hardware.
    require(os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'RUN_ATTEMPT_REPLAY_DENIED')
    require(os.geteuid() != 0 and os.environ.get('RUNNER_NAME') == dispatch.EXPECTED_RUNNER
            and os.environ.get('RUNNER_ENVIRONMENT') == 'self-hosted', 'NONROOT_APPROVED_RUNNER_REQUIRED')
    event = dispatch.parse_json(Path(os.environ.get('GITHUB_EVENT_PATH','/nonexistent')))
    req = dispatch.request(event, os.environ)
    registry = dispatch.parse_json(ROOT/'specs/engineering-dispatch/development-tasks-v1.json')
    order = dispatch.parse_dynamic_work_order(event)
    dispatch.authorize(event, os.environ, registry, pr_info=dispatch.live_pr_metadata(req))
    sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,timeout=5).strip()
    require(req['source_sha'] == sha, 'SOURCE_SHA_MISMATCH')
    if order['execution_path'] == 'path2-cli':
        require(order['capability'] == 'operator-cli' and order['scope'] == 'guarded-hardware'
                and order['script'] == 'scripts/plasma_programming_load.py'
                and order['argv'] == argv, 'OWNER_COMMAND_MISMATCH')
        require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,timeout=5),
                'REVIEWED_SOURCE_DIRTY')
    else:
        # Only this bounded engineering assignment permits an ephemeral candidate HIL.
        require(order.get('codex_execution') == 'guarded-hardware-no-sandbox'
                and dispatch.work_order_digest(order) ==
                'e2ed84f253b454b687f410b0b9c9df838abd0497e77c4ccefc0960e9c14c35ee',
                'ENGINEERING_ORDER_MISMATCH')
    return dict(source_sha=sha,work_order_sha256=dispatch.work_order_digest(order),
                execution_path=order['execution_path'],run_id=os.environ.get('GITHUB_RUN_ID'),
                runner=os.environ.get('RUNNER_NAME'),uid=os.geteuid(),
                script_sha256=digest(Path(__file__).read_bytes()),
                dispatcher_timeout_seconds=order.get('timeout_seconds'))


def check_remote(observed, cfg):
    z, conf = observed['metadata'], observed['config']
    require(not observed['seals'] and not observed['admissions'] and not z['openocd_pids'],
            'SEALED_OR_BUSY_OR_ADMITTED')
    require(conf['ppu']['id'] == 'z2-hil' and conf['server']['max_concurrent_jobs'] >= 2,
            'PPU_CONCURRENCY_OR_IDENTITY_MISMATCH')
    for site in (1,2):
        s = next(s for s in conf['sites'] if s['id'] == site)
        require(s['enabled'] is True and s['target'] == TARGET and s['interface'] == 'openocd',
                'INSTALLED_TARGET_MISMATCH')
    require(z['engine']['status'] == 'VERIFIED' and z['engine']['driver'] == 'plasma_swd'
            and z['engine']['abi'] == 5 and z['fpga']['status'] == 'IMAGE'
            and z['fpga']['boot_match'] is True and z['fpga']['manager_state'] == 'operating'
            and z['fpga']['image_id'] == cfg['fpga_image_id'], 'ROOT_ENGINE_OR_BOOT_NOT_VERIFIED')
    require(all(z['services'][n]['ActiveState'] == 'active' for n in
                ('plasma-server','plasma-site-worker','plasma-bootstrap')), 'REQUIRED_SERVICE_UNAVAILABLE')


def fixture_observation(cfg):
    serials = [p.name for p in Path('/dev/serial/by-id').glob('usb-PLASMA_Lab_PLASMA_Blue_Pill_CDC_*')]
    require(all(re.fullmatch(r'[A-F0-9]{12}',v) and sum(v in n for n in serials) == 1
                for v in cfg['fixture']) and len(set(cfg['fixture'])) == 2,
            'DUT_FIXTURE_NOT_PRESENT')
    # An independent ST-LINK control group must not drive alongside Z2.
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            require((p/'comm').read_text().strip() != 'openocd', 'SWPC_OPENOCD_ACTIVE')
        except (FileNotFoundError, ProcessLookupError):
            pass
    return serials


def measure(args, argv, *, client=None, remote=None, authenticate=authorization):
    output = Path(args.output)
    require(not output.is_symlink(), 'OUTPUT_SYMLINK_DENIED')
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not any(output.iterdir()), 'OUTPUT_NOT_EMPTY')
    require(output.stat().st_uid == os.geteuid() and stat.S_IMODE(output.stat().st_mode) == 0o700,
            'OUTPUT_OWNER_OR_MODE_INVALID')
    # Exclusive, never-reused output is also the local exactly-once execution claim.
    claim = os.open(output/'submission-journal.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(claim)
    report = dict(schema=SCHEMA,outcome='NOT_RUN',batch_post_count=0,start_post_count=0,
                  hardware='NOT_RUN',reset_run='EXISTING_POST_PROGRAM_RESET_RUN_ACCEPTED',
                  source_sha=None,blocker=None)
    def save():
        atomic_json(output/'submission-journal.json',report)
    def receipt(name, data):
        atomic_json(output/(name+'.json'),data)
        return data
    observer = None
    sampler = None
    interrupted = threading.Event()
    deadline = time.monotonic()+args.timeout_sec
    previous_handlers = {}
    def interrupt(signum, frame):
        interrupted.set()
    def bounded():
        require(not interrupted.is_set(), 'INTERRUPTED')
        require(time.monotonic() < deadline, 'BENCHMARK_TIMEOUT')
    try:
        if not args.run_batch:
            report['blocker'] = 'EXPLICIT_RUN_BATCH_REQUIRED'
            return report
        report.update(authenticate(argv));save()
        require_hardware_claim(report);save()
        if report.get('execution_path') == 'path2-cli':
            require(report['dispatcher_timeout_seconds'] >= args.timeout_sec+120,'DISPATCH_TIMEOUT_TOO_SHORT')
        raw = Path(args.config).read_bytes()
        require(len(raw) <= 16384 and digest(raw) == args.config_sha256, 'CONFIG_DIGEST_MISMATCH')
        cfg = json.loads(raw)
        require(all(HEX64.fullmatch(cfg[k]) for k in
                    ('image_sha256','asset_set_sha256','resource_set_sha256')), 'CONFIG_IDENTITY_INVALID')
        # Fixture association is owner-provided, digest-bound in the admitted argv.
        require(isinstance(cfg['fixture'],list) and len(cfg['fixture']) == 2, 'FIXTURE_IDENTITY_REQUIRED')
        report['configuration_sha256'] = digest(raw)
        report['fixture'] = cfg['fixture']
        report['fixture_observed'] = fixture_observation(cfg)
        report['fixture_basis'] = 'observed CDC pair; accepted Site SWD wiring reused; no CDC-to-Site mapping inferred'
        image = Path(cfg['image']).read_bytes()
        require(0 < len(image) <= 65536 and digest(image) == cfg['image_sha256'], 'IMAGE_MISMATCH')
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',cfg['image_filename'])
                and re.fullmatch(r'/opt/plasma/python/[A-Za-z0-9._-]+/bin/python3',cfg['z2_python']),
                'CONFIG_PATH_INVALID')
        client = client or HTTP(cfg['manager'])
        remote = remote or Remote()
        remote.deadline = deadline+110
        client.deadline = deadline+110
        for sig in (signal.SIGINT,signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig,interrupt)
        prefix = '/api/ppus/z2/gateway'
        def get(name,path):
            bounded()
            return receipt(name,client.request('GET',path))
        def preflight():
            idle(get('pre-status',prefix+'/api/status'))
            boot = get('pre-bootstrap','/api/registry/z2/bootstrap')
            require(boot['pairing']['device_authenticated'] is True and
                    boot['pairing']['device_id'] == cfg['device_id'] and
                    boot['bootstrap']['runtime']['git_sha'] == cfg['deployed_sha'], 'DEPLOYED_IDENTITY_MISMATCH')
            observed = receipt('pre-root',remote.inspect())
            check_remote(observed,cfg)
            report['deployed_identity'] = dict(source_sha=cfg['deployed_sha'],device_id=cfg['device_id'],
                    asset_set_sha256=cfg['asset_set_sha256'],generation=cfg['generation'],
                    resource_set_sha256=cfg['resource_set_sha256'],fpga=observed['metadata']['fpga'])
        preflight()
        image_body = dict(icpn=TARGET,operations=OPERATIONS,image_base64=base64.b64encode(image).decode(),
                          image_filename=cfg['image_filename'])
        for site in (1,2):
            bounded()
            plan = receipt('plan-site%d'%site,client.request('POST',
                    '/api/registry/z2/bootstrap/programming/plans',{**image_body,'site_id':site}))['plan']
            check_plan(plan,cfg,site,image)
        # The existing dispatcher owns durable event admission. Also prevent a
        # second local invocation in this run BEFORE any Z2 or Start side effect.
        claim_path = Path(os.environ['RUNNER_TEMP'])/('plasma-loading-'+report['work_order_sha256']+'.claim')
        with claim_path.open('x') as claim_file:
            os.chmod(claim_path,0o600)
            json.dump(dict(source_sha=report['source_sha'],journal=str((output/'submission-journal.json').resolve())),claim_file)
            claim_file.flush();os.fsync(claim_file.fileno())
        observer = remote.launch(cfg,args)
        report['observer'] = observer;save()
        ready_deadline = time.monotonic()+20
        def status():
            bounded()
            state = remote.status(observer)
            require(state['alive'] and not state['finished'], 'OBSERVER_EXITED')
            require(not state.get('latest') or not state['latest']['errors'], 'OBSERVER_SAMPLE_ERRORS')
            return state
        state = status()
        while not state['ready']:
            require(time.monotonic() < ready_deadline, 'OBSERVER_NOT_READY')
            interrupted.wait(.5);state = status()
        ready = receipt('observer-ready',state)['ready']
        require(not ready['processes'], 'OPENOCD_BEFORE_BATCH')
        while state['latest']['monotonic_s']-ready['monotonic_s'] < args.baseline_sec:
            require(not state['latest']['processes'], 'OPENOCD_DURING_IDLE_BASELINE')
            interrupted.wait(.5);state = status()
        preflight()  # Recheck after baseline, before the only submission.
        bounded()
        report['start_post_count'] = 1;report['start_issuance'] = 'UNKNOWN';save()
        # A lost Start response is harmless (random ID, nobody holds it; expires),
        # but stays UNKNOWN rather than a plain NOT_RUN.
        issued = receipt('start-response',client.request('POST','/api/programming/starts',{'kind':'batch'}))
        report['start_issuance'] = 'ISSUED'
        start = issued['start']['start_id']
        require(ID.fullmatch(start), 'START_ID_INVALID')
        report['start_id'] = start;save()
        state = status()
        submitted = state['latest']['monotonic_s']
        report['before_post_sample'] = state['latest']
        report['clock_bounds'] = dict(submitted=submitted,terminal=None,recovery_start=None)
        report['batch_post_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        body = dict(image_body,start_id=start,targets=[{'ppu_alias':'z2','site_ids':[1,2]}],
                    repeat=1,retry_limit=0,stop_policy={'kind':'never'})
        receipt('batch-request',{k:v for k,v in body.items() if k != 'image_base64'})
        batch_id = submit_once(client,body,report,save)
        report['hardware'] = 'SUBMITTED';save()
        batch = get('batch-latest','/api/programming/batches/'+batch_id)['batch']
        while batch.get('outcome') not in TERMINAL:
            interrupted.wait(.5);status()
            batch = get('batch-latest','/api/programming/batches/'+batch_id)['batch']
        receipt('batch-final',batch)
        state = status();terminal = state['latest']['monotonic_s']
        report['clock_bounds']['terminal'] = terminal
        jobs = []
        for unit in batch['units']:
            for attempt in unit.get('attempts',[]):
                if attempt.get('run_id'):
                    get('run-site%d'%unit['site_id'],'/api/registry/z2/bootstrap/programming/runs/'+quote(attempt['run_id'],safe=''))
                if attempt.get('job_id'):
                    job = get('job-site%d'%unit['site_id'],prefix+'/api/status?job='+quote(attempt['job_id'],safe=''))['job']
                    jobs.append((unit['site_id'],job))
        get('start-reconciled','/api/programming/starts/'+start)
        while state['latest']['processes']:
            interrupted.wait(.5);state=status()
        recovery_start = state['latest']['monotonic_s']
        while state['latest']['monotonic_s']-recovery_start < args.recovery_sec:
            require(not state['latest']['processes'], 'OPENOCD_DURING_RECOVERY')
            interrupted.wait(.5);state=status()
        idle(get('final-status',prefix+'/api/status'))
        check_remote(receipt('final-root',remote.inspect()),cfg)
        report['final_idle'] = True
        report['batch_outcome'] = batch['outcome']
        report['clock_bounds'] = dict(submitted=submitted,terminal=terminal,recovery_start=recovery_start)
        report['site_results'] = [site_result(job,site,cfg) for site,job in jobs]
        summaries=[]
        for site,job in jobs:
            summaries.append(check_job(job,site,cfg))
        require(sorted(j['site_id'] for j in summaries)==[1,2] and batch['outcome']=='PASS', 'BATCH_OR_SITE_FAILED')
        report['jobs'] = summaries
        elapsed = terminal-submitted
        report['throughput'] = dict(bytes=sum(j['bytes'] for j in summaries),elapsed_s=elapsed,
                                   bytes_per_s=sum(j['bytes'] for j in summaries)/elapsed)
        report['outcome'] = 'PASS'
    except Exception as exc:
        report['blocker'] = str(exc) if isinstance(exc,Blocked) else type(exc).__name__
        report['outcome'] = ('NOT_RUN' if not report['batch_post_count']
                             or report.get('submission') == 'NOT_ACCEPTED' else 'OUTCOME_UNKNOWN')
        if report.get('batch_outcome') in TERMINAL - {'OUTCOME_UNKNOWN'}:
            report['outcome'] = 'FAIL'
    finally:
        # Stop only this Batch's future queueing on interruption/failure. The
        # canonical Worker retains ownership and SAFE_OFF of already running Jobs.
        # Never kill OpenOCD or release another owner's lease from this tool.
        if report['outcome'] == 'OUTCOME_UNKNOWN' and report.get('start_id'):
            try:
                rec = receipt('cleanup-reconciliation',client.request('GET',
                              '/api/programming/starts/'+report['start_id']))['reconciliation']
                existing = rec.get('batch') or {}
                if existing.get('start_id') == report['start_id'] and ID.fullmatch(existing.get('batch_id','')):
                    report['batch_id'] = existing['batch_id']
                    if existing.get('outcome') not in TERMINAL:
                        report['stop_post_count'] = 1;save()
                        receipt('cleanup-stop',client.request('POST',
                            '/api/programming/batches/'+existing['batch_id']+'/stop',{'stop':'STOP_QUEUING'}))
                        until = time.monotonic()+30
                        while time.monotonic() < until:
                            existing = receipt('cleanup-batch',client.request('GET',
                                '/api/programming/batches/'+existing['batch_id']))['batch']
                            if existing.get('outcome') in TERMINAL:
                                break
                            time.sleep(.5)
                    report['cleanup_batch_outcome'] = existing.get('outcome')
                final = receipt('cleanup-status',client.request('GET','/api/ppus/z2/gateway/api/status'))
                idle(final)
                report['final_idle'] = True
            except Exception as exc:
                report['hardware_cleanup'] = str(exc) if isinstance(exc,Blocked) else type(exc).__name__
        if observer is not None:
            try:
                remote.status(observer,stop=True)
                for _ in range(40):
                    state=remote.status(observer)
                    if state['finished']:
                        break
                    time.sleep(.25)
                require(state['finished'], 'OBSERVER_CLEANUP_UNCONFIRMED')
                sampler = remote.collect(observer,output)
                report['ephemeral_cleanup'] = remote.remove(observer)
                report['observer_termination'] = sampler['termination']
                report['observer_average_cpu_one_core'] = sampler['observer_average_cpu_pct_one_core']
                if report.get('clock_bounds'):
                    c=report['clock_bounds']
                    report['comparison'] = comparison(sampler['frames'],c['submitted'],c['terminal'] or float('inf'),c['recovery_start'] or float('inf'),args.interval_ms/1000)
                    p=report['comparison']['phases']
                    report['measurement_insufficient'] = (p['idle']['duration_s'] < args.baseline_sec
                                                          or p['recovery']['duration_s'] < args.recovery_sec)
                    if report['outcome'] == 'PASS' and report['measurement_insufficient']:
                        report['outcome']='INSUFFICIENT_SAMPLES'
                    elif report['outcome'] == 'PASS' and not report['comparison']['sampled_pid_overlap_s']:
                        report['outcome']='NOT_OBSERVED'
            except Exception as exc:
                report['cleanup'] = str(exc) if isinstance(exc,Blocked) else type(exc).__name__
                # Measurement evidence failed; a known hardware outcome stays known.
                report['outcome'] = ('FAIL' if report.get('batch_outcome') in TERMINAL - {'OUTCOME_UNKNOWN'}
                                     else 'NOT_RUN' if not report['batch_post_count']
                                     or report.get('submission') == 'NOT_ACCEPTED' else 'OUTCOME_UNKNOWN')
        for sig,handler in previous_handlers.items():
            signal.signal(sig,handler)
        trace(report)
        save()
        atomic_json(output/'report.json',report)
        paths = sorted(p for p in output.iterdir() if p.is_file() and p.name != 'SHA256SUMS')
        with (output/'SHA256SUMS').open('w') as f:
            for p in paths:
                f.write(digest(p.read_bytes())+'  '+p.name+'\n')
    if report.get('comparison'):
        phase_csv(output,report['comparison'])
        write_hashes(output)
    if report.get('execution_path') == 'path2-cli':
        created = []
        try:
            import tarfile
            artifact = Path(os.environ['RUNNER_TEMP'])/'plasma-path2-loading-benchmark.tar.gz'
            with artifact.open('xb') as stream:
                created.append(artifact)
                os.chmod(artifact,0o600)
                with tarfile.open(fileobj=stream,mode='w:gz') as archive:
                    for path in sorted(output.iterdir()):
                        require(path.is_file() and not path.is_symlink(), 'ARTIFACT_ENTRY_INVALID')
                        archive.add(path,arcname=path.name,recursive=False)
            with artifact.with_suffix(artifact.suffix+'.sha256').open('x') as sidecar:
                created.append(artifact.with_suffix(artifact.suffix+'.sha256'))
                sidecar.write(digest(artifact.read_bytes())+'  '+artifact.name+'\n')
        except Exception as exc:
            # Do not publish an archive whose report predates this failure.
            for path in created:
                path.unlink(missing_ok=True)
            report['artifact_error'] = type(exc).__name__
            if report['outcome'] not in ('OUTCOME_UNKNOWN', 'NOT_RUN'):
                report['outcome'] = 'FAIL'
            save()
            atomic_json(output/'report.json',report)
            write_hashes(output)
    return report


def write_hashes(output):
    with (output/'SHA256SUMS').open('w') as stream:
        for path in sorted(output.iterdir()):
            if path.is_file() and path.name != 'SHA256SUMS':
                stream.write(digest(path.read_bytes())+'  '+path.name+'\n')


def phase_csv(output, comparison):
    fields=['phase','n','duration_s','quality','cpu_mean','cpu_p95','cpu_peak','ram_mean_kib',
            'ram_p95_kib','ram_peak_kib','cpu_mean_delta_pp','ram_mean_delta_pp','cpu_headroom_pct']
    with (output/'phases.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for phase,p in comparison['phases'].items():
            writer.writerow(dict(phase=phase,n=p['n'],duration_s=p['duration_s'],quality=p['quality'],
                cpu_mean=p['cpu_pct']['mean'],cpu_p95=p['cpu_pct']['p95'],cpu_peak=p['cpu_pct']['peak'],
                ram_mean_kib=p['ram_used_kib']['mean'],ram_p95_kib=p['ram_used_kib']['p95'],
                ram_peak_kib=p['ram_used_kib']['peak'],cpu_mean_delta_pp=p['cpu_delta_pp']['mean'],
                ram_mean_delta_pp=p['ram_delta_pp']['mean'],cpu_headroom_pct=p['cpu_headroom_pct']))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    p = sub.add_parser('measure',help='one guarded Batch; no --run-batch means NOT_RUN without network')
    p.add_argument('--ppu',choices=['z2'],default='z2')
    p.add_argument('--sites',choices=['1,2'],default='1,2')
    p.add_argument('--baseline-sec',type=int,default=15)
    p.add_argument('--interval-ms',type=int,default=250)
    p.add_argument('--recovery-sec',type=int,default=15)
    p.add_argument('--timeout-sec',type=int,default=180)
    p.add_argument('--run-batch',action='store_true')
    p.add_argument('--config',help='digest-bound private lab configuration (see usage)')
    p.add_argument('--config-sha256')
    p.add_argument('--output',default='.plasma-path3-evidence/loading-benchmark',help='new private evidence directory')
    p = sub.add_parser('sample',help='Z2-local read-only /proc sampler; no DUT or HTTP')
    p.add_argument('--interval',type=float,default=.25)
    p.add_argument('--duration',type=float,default=180)
    p.add_argument('--output',required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.command == 'sample':
        if not (.1 <= args.interval <= 5 and 1 <= args.duration <= 1800):
            parser.error('sampler bounds: interval 0.1..5, duration 1..1800 seconds')
        sample(args)
        return 0
    if not (15 <= args.baseline_sec <= 120 and 15 <= args.recovery_sec <= 120
            and 100 <= args.interval_ms <= 1000 and args.baseline_sec+args.recovery_sec+30 <= args.timeout_sec <= 1620):
        parser.error('require baseline/recovery 15..120s, interval 100..1000ms, timeout baseline+recovery+30..1620s')
    if args.run_batch and (not args.config or not args.config_sha256 or not HEX64.fullmatch(args.config_sha256)):
        parser.error('--run-batch requires --config and --config-sha256')
    os.umask(0o077)
    report_existed = (Path(args.output)/'report.json').exists()
    try:
        result = measure(args,argv)
    except Exception as exc:
        result = dict(schema=SCHEMA,outcome='NOT_RUN',blocker=str(exc) if isinstance(exc,Blocked) else type(exc).__name__)
        saved = Path(args.output)/'report.json'
        if not report_existed and saved.is_file():
            prior = json.loads(saved.read_text())
            if prior.get('batch_post_count'):
                result.update(outcome='OUTCOME_UNKNOWN',source_sha=prior.get('source_sha'),
                              start_id=prior.get('start_id'),batch_id=prior.get('batch_id'))
    # Large CSV/JSON remain artifacts; stdout is always a small non-secret receipt.
    print(json.dumps({k:result.get(k) for k in ('schema','outcome','blocker','source_sha','start_id','batch_id')},separators=(',',':')))
    return 0 if result['outcome']=='PASS' else 69 if result['outcome']=='NOT_RUN' else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Host-only crash/failure injection. No SSH, board, service or physical MMIO."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pl.hil.ms01 import supervisor as s


@pytest.fixture
def plan():
    return s.Plan({'fpga_source_sha':'1'*40,'runtime_source_sha':'2'*40},'a'*64,{})


class Fake:
    def __init__(self,j,fail=None,crash=None,bindings=None):
        self.j=j;self.fail=fail;self.crash=crash;self.calls=[];self.gate=False
        self.bindings=bindings or {d:s.DRIVER for d in s.DEVICES}
        self.original=dict(self.bindings);self.image='base';self.alive=False;self.terminal=True
    def step(self,name):
        self.calls.append(name)
        if name==self.crash: raise SystemExit('simulated supervisor SIGKILL')
        if name==self.fail: raise s.Stop('injected '+name)
    def claim_mmio(self): self.step('claim');self.gate=True
    def release_mmio(self): self.step('release');self.gate=False
    def snapshot(self): self.step('snapshot');return {'bindings':dict(self.bindings)}
    def quiescent(self,allowed):
        self.step('ownership');assert self.gate
        assert {k for k,v in self.bindings.items() if v}<=allowed
    def unbind(self,device,driver):
        assert self.j.state['phase']=='UNBIND_INTENT'
        self.step('unbind:'+device);self.bindings[device]=None
    def candidate(self):
        assert self.gate and self.j.state['image_touched']
        self.image='candidate';self.step('load')
    def receipt(self): self.step('receipt');assert self.image=='candidate'
    def worker(self):
        assert not self.gate and self.image=='candidate';self.step('worker')
    def child_dead(self,child):
        self.step('child-dead');s.require(not self.alive,'child remains alive')
    def child_terminal(self,state):
        if not self.terminal: raise s.UnsafeStall('missing child terminal')
    def restore(self):
        assert self.gate and self.j.state['phase']=='RESTORE_INTENT'
        self.step('restore');self.image='base'
    def bind(self,device,driver):
        assert self.j.state['phase']=='REBIND_INTENT'
        self.step('bind:'+device);self.bindings[device]=driver
    def verify(self,original):
        self.step('verify')
        return {'image':self.image=='base','bindings':self.bindings==original['bindings']}


def setup(tmp_path,plan,**kw):
    j=s.Journal(tmp_path/'session',create=True,plan=plan);a=Fake(j,**kw)
    return s.Controller(a,j,plan),a,j


def test_success_requires_independent_restore(tmp_path,plan):
    c,a,j=setup(tmp_path,plan);r=c.run()
    assert r['result']==r['data_test']==r['recovery']=='PASS'
    assert a.image=='base' and a.bindings==a.original
    assert a.calls.index('release')<a.calls.index('worker')<a.calls.index('restore')
    assert a.calls[-1]=='verify'
    assert s.Journal(j.output).state==r


@pytest.mark.parametrize('stage',['load','receipt','worker'])
def test_normal_process_mmio_or_load_failure_restores_without_retry(tmp_path,plan,stage):
    c,a,j=setup(tmp_path,plan,fail=stage);r=c.run()
    assert r['result']=='FAIL' and r['recovery']=='PASS'
    assert a.calls.count(stage)==1 and a.calls.count('restore')==1
    assert a.image=='base' and a.bindings==a.original


@pytest.mark.parametrize('stage',['load','receipt','worker','restore','bind:'+s.DEVICES[0]])
def test_fatal_supervisor_exit_can_explicitly_resume_recovery(tmp_path,plan,stage):
    c,a,j=setup(tmp_path,plan,crash=stage)
    with pytest.raises(SystemExit): c.run()
    assert j.state['image_touched']
    a.crash=None;a.j=s.Journal(j.output)
    r=s.Controller(a,a.j,plan).recover()
    assert r['recovery']=='PASS' and a.image=='base' and a.bindings==a.original
    assert a.calls.count('worker')<=1  # Recovery NEVER reruns the benchmark.


def test_surviving_child_blocks_new_load(tmp_path,plan):
    c,a,j=setup(tmp_path,plan,fail='worker');a.alive=True;r=c.run()
    assert r['phase']=='RECOVERY_FAILED' and r['recovery']=='FAIL'
    assert 'restore' not in a.calls and not any(v.startswith('bind:') for v in a.calls)


@pytest.mark.parametrize('stage',['load','worker'])
def test_axi_or_loader_stall_is_never_called_automatic_recovery(tmp_path,plan,stage):
    c,a,j=setup(tmp_path,plan)
    original=a.step
    def stall(name):
        original(name)
        if name==stage: raise s.UnsafeStall('injected uninterruptible syscall')
    a.step=stall;r=c.run()
    assert r['phase']=='EXTERNAL_RECOVERY_REQUIRED'
    assert r['recovery']=='NOT_RUN' and 'restore' not in a.calls
    with pytest.raises(s.Stop,match='external recovery'): c.recover()


def test_absent_terminal_after_supervisor_crash_prevents_reload(tmp_path,plan):
    c,a,j=setup(tmp_path,plan,crash='worker')
    with pytest.raises(SystemExit): c.run()
    a.crash=None;a.terminal=False
    r=c.recover();assert r['phase']=='EXTERNAL_RECOVERY_REQUIRED'
    assert 'restore' not in a.calls


def test_recovery_failure_does_not_rebind_driver_on_unknown_image(tmp_path,plan):
    c,a,j=setup(tmp_path,plan,fail='restore');r=c.run()
    assert r['result']==r['recovery']=='FAIL'
    assert not any(v.startswith('bind:') for v in a.calls)
    assert a.image=='candidate'


def test_rebind_failure_attempts_other_original_bindings_and_remains_fail(tmp_path,plan):
    c,a,j=setup(tmp_path,plan,fail='bind:'+s.DEVICES[0]);r=c.run()
    assert r['recovery']=='FAIL' and a.image=='base'
    assert 'bind:'+s.DEVICES[1] in a.calls and 'verify' in a.calls
    assert r['result']=='FAIL'


def test_originally_unbound_driver_remains_unbound(tmp_path,plan):
    c,a,j=setup(tmp_path,plan,bindings={s.DEVICES[0]:s.DRIVER,s.DEVICES[1]:None})
    assert c.run()['recovery']=='PASS'
    assert 'unbind:'+s.DEVICES[1] not in a.calls and a.bindings[s.DEVICES[1]] is None


def test_verification_failure_cannot_be_promoted_to_pass(tmp_path,plan):
    c,a,j=setup(tmp_path,plan);a.verify=lambda _: {'metadata':False,'UIO':True}
    assert c.run()['result']=='FAIL'
    assert j.state['phase']=='RECOVERY_FAILED'


def test_preflight_failure_has_no_hardware_mutations(tmp_path,plan):
    c,a,j=setup(tmp_path,plan,fail='ownership');r=c.run()
    assert r['phase']=='NO_GO' and r['recovery']=='NOT_NEEDED'
    assert not any(v in a.calls for v in ('load','worker','restore'))
    assert not any(v.startswith(('bind:','unbind:')) for v in a.calls)


def test_global_owner_conflict_before_reload_cannot_be_bypassed(tmp_path,plan):
    c,a,j=setup(tmp_path,plan);original=a.claim_mmio
    def claim():
        if 'worker' in a.calls: raise BlockingIOError('another MMIO owner')
        original()
    a.claim_mmio=claim;r=c.run()
    assert r['phase']=='RECOVERY_FAILED' and 'restore' not in a.calls


def test_atomic_checkpoint_survives_unpublished_partial_write(tmp_path,plan):
    j=s.Journal(tmp_path/'session',create=True,plan=plan);j.save('ONE')
    (j.output/'.pending-0002-old').write_text('{truncated')
    fresh=s.Journal(j.output);assert fresh.state['phase']=='ONE';fresh.save('TWO')
    assert s.Journal(j.output).state['phase']=='TWO'


def test_default_dry_run_never_instantiates_hardware_or_creates_output(tmp_path,plan,monkeypatch):
    monkeypatch.setattr(s.Plan,'read',lambda *_:plan)
    monkeypatch.setattr(s,'LinuxAdapter',lambda *_:pytest.fail('hardware adapter in dry-run'))
    out=tmp_path/'unused'
    args=['--plan',str(tmp_path/'plan'),'--expected-plan-sha256','a'*64,'--output',str(out)]
    assert s.main(args)==0 and not out.exists()
    assert s.main(args+['--recover-only'])==0 and not out.exists()
    assert s.main(args+['--execute-live'])==2 and not out.exists()
    assert s.main(args+['--ack-unrecoverable-axi-stall-risk'])==2 and not out.exists()


@pytest.mark.parametrize('code,kind', [('pass','ok'),('raise RuntimeError("injected")','failure'),
    ('import os,signal; os.kill(os.getpid(),signal.SIGKILL)','signal'),
    ('import time;time.sleep(5)','timeout')])
def test_real_host_child_completion_and_crash_no_instrument(tmp_path,plan,code,kind):
    j=s.Journal(tmp_path/'session',create=True,plan=plan);j.save('BEFORE')
    a=s.LinuxAdapter(plan,j);a.config_fd=s.lock_file(tmp_path/'config-lock')
    a.mmio_fd=s.lock_file(tmp_path/'owner-lock')
    try:
        if kind=='ok': a._child('offline-only',code,2)
        else:
            with pytest.raises(s.Stop): a._child('offline-only',code,.1 if kind=='timeout' else 2)
        terminal=j.output/j.state['child_terminal']
        assert terminal.exists()==(kind in ('ok','failure'))
        if kind in ('signal','timeout'):
            with pytest.raises(s.UnsafeStall): a.child_terminal(j.state)
        # Child completion never releases the parent's global owner gate.
        with pytest.raises(BlockingIOError): s.lock_file(tmp_path/'owner-lock')
    finally:
        a.__exit__(None,None,None)


def test_inherited_configuration_lease_survives_parent_close(tmp_path,plan):
    j=s.Journal(tmp_path/'session',create=True,plan=plan);a=s.LinuxAdapter(plan,j)
    path=tmp_path/'config-lock';a.config_fd=s.lock_file(path)
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.3)'],pass_fds=(a.config_fd,))
    a.__exit__(None,None,None)
    try:
        with pytest.raises(BlockingIOError): s.lock_file(path)
    finally: child.wait(timeout=3)
    fd=s.lock_file(path);os.close(fd)


@pytest.fixture
def plan_files(tmp_path,monkeypatch):
    files={k:str(tmp_path/k) for k in ('manifest','bit','hwh','candidate_bin','recovery_bin','recovery_hwh')}
    for name in files.values():Path(name).write_bytes(b'1234')
    Path(files['candidate_bin']).write_bytes(b'4321'+bytes.fromhex('00000020'))
    data={**files,'fpga_source_sha':'1'*40,'runtime_source_sha':'2'*40,'runtime_files':s.runtime_files(),
          'manifest_sha256':'a'*64,'candidate_bin_sha256':s.digest(Path(files['candidate_bin'])),
          'recovery_bin_sha256':s.n.swd04_contract.RECOVERY_BIN_SHA256,
          'recovery_hwh_sha256':s.n.swd04_contract.RECOVERY_HWH_SHA256,
          'iterations':8,'trials':3,'payload_sizes':[2048,8192,65536],'worker_timeout_s':900,
          'health_urls':{'gateway_live':'http://127.0.0.1:18080/api/health/live',
                        'gateway_ready':'http://127.0.0.1:18080/api/health/ready',
                        'bootstrap':'http://127.0.0.1:18081/v1/health',
                        'jupyter_login':'http://127.0.0.1:9090/login',
                        'jupyter_api':'http://127.0.0.1:9090/api'}}
    monkeypatch.setattr(s.n,'verify_artifacts',lambda **_: {'source_git_sha':'1'*40})
    monkeypatch.setattr(s,'bit_payload',lambda _:b'1234')
    return data,tmp_path/'plan.json'


def test_pinned_plan_and_separate_runtime_revision(plan_files):
    data,p=plan_files;s.write_new(p,data);v=s.Plan.read(p,s.digest(p))
    assert v.data['fpga_source_sha']!=v.data['runtime_source_sha']
    with pytest.raises(s.Stop,match='digest'):s.Plan.read(p,'0'*64)


@pytest.mark.parametrize('key,value', [('fpga_source_sha','3'*40),('runtime_files',{}),
    ('recovery_bin_sha256','b'*64),('payload_sizes',[0]),('trials',4),('iterations',0),
    ('worker_timeout_s',0),('health_urls',{})])
def test_plan_faults_fail_before_adapter(plan_files,key,value):
    data,p=plan_files;data[key]=value;s.write_new(p,data)
    with pytest.raises(s.Stop):s.Plan.read(p,s.digest(p))


def test_bad_bin_conversion(plan_files):
    data,p=plan_files;Path(data['candidate_bin']).write_bytes(b'wrong');s.write_new(p,data)
    with pytest.raises(s.Stop,match='conversion'):s.Plan.read(p,s.digest(p))


def test_changed_boot_blocks_control_writes(tmp_path,plan):
    j=s.Journal(tmp_path/'session',create=True,plan=plan)
    j.save('OLD_BOOT',original={'boot_id':'not-this-boot'})
    a=s.LinuxAdapter(plan,j)
    for call in (lambda:a.quiescent(frozenset()),lambda:a._program('base.bin'),
                 lambda:a.unbind(s.DEVICES[0],s.DRIVER),lambda:a.bind(s.DEVICES[0],s.DRIVER)):
        with pytest.raises(s.Stop,match='Boot changed'):call()


def test_actual_uio_adapter_preserves_and_verifies_bindings_offline(tmp_path,plan,monkeypatch):
    j=s.Journal(tmp_path/'session',create=True,plan=plan);a=s.LinuxAdapter(plan,j)
    a.platform_root=tmp_path/'platform';driver=a.platform_root/'drivers'/s.DRIVER
    driver.mkdir(parents=True)
    for command in ('bind','unbind'):(driver/command).touch()
    for device in s.DEVICES:
        p=a.platform_root/'devices'/device;p.mkdir(parents=True)
        (p/'driver').symlink_to(driver)
    writes=[];original=Path.write_text
    def sysfs(path,value,*args,**kwargs):
        if path.parent==driver and path.name in ('bind','unbind'):
            writes.append((path.name,value));link=a.platform_root/'devices'/value/'driver'
            if path.name=='unbind':link.unlink()
            else:link.symlink_to(driver)
            return len(value)
        return original(path,value,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',sysfs)
    a.unbind(s.DEVICES[0],s.DRIVER);assert a._driver(s.DEVICES[0]) is None
    a.bind(s.DEVICES[0],None);assert len(writes)==1
    a.bind(s.DEVICES[0],s.DRIVER);a.bind(s.DEVICES[0],s.DRIVER)
    assert writes==[('unbind',s.DEVICES[0]),('bind',s.DEVICES[0])]
    # A sysfs write returning success without an observed binding is not success.
    a.unbind(s.DEVICES[0],s.DRIVER)
    monkeypatch.setattr(Path,'write_text',lambda *_:0)
    with pytest.raises(s.Stop,match='Rebind not observed'):a.bind(s.DEVICES[0],s.DRIVER)
    wrong=a.platform_root/'drivers/unexpected';wrong.mkdir()
    (a.platform_root/'devices'/s.DEVICES[0]/'driver').symlink_to(wrong)
    with pytest.raises(s.Stop,match='Unexpected original'):a.bind(s.DEVICES[0],s.DRIVER)


def test_live_flags_on_host_reject_before_journal(tmp_path,plan,monkeypatch):
    monkeypatch.setattr(s.Plan,'read',lambda *_:plan)
    monkeypatch.setattr(s.os,'geteuid',lambda:0)
    def reject():raise s.Stop('not ARMv7 target')
    monkeypatch.setattr(s.n,'check_runtime',reject)
    out=tmp_path/'unused'
    assert s.main(['--plan','unused','--expected-plan-sha256','a'*64,'--output',str(out),
                   '--execute-live','--ack-unrecoverable-axi-stall-risk'])==2
    assert not out.exists()


def test_crash_during_unbind_recovers_bindings_without_fpga_reload(tmp_path,plan):
    c,a,j=setup(tmp_path,plan,crash='unbind:'+s.DEVICES[1])
    with pytest.raises(SystemExit):c.run()
    a.crash=None;r=c.recover()
    assert r['recovery']=='PASS' and a.bindings==a.original
    assert not any(v in a.calls for v in ('load','restore','worker'))


def test_absent_verification_is_not_recovery_pass(tmp_path,plan):
    c,a,j=setup(tmp_path,plan);a.verify=lambda _:{}
    assert c.run()['recovery']=='FAIL'


def test_old_load_log_cannot_prove_new_manager_load(tmp_path,plan,monkeypatch):
    j=s.Journal(tmp_path/'session',create=True,plan=plan);a=s.LinuxAdapter(plan,j)
    a.mmio_fd=123  # Sentinel only: this test opens no device or actual control lock.
    monkeypatch.setattr(a,'_child',lambda *_:None)
    monkeypatch.setattr(a,'_cmd',lambda _: '[1] fpga_manager fpga0: writing base.bin to Xilinx Zynq FPGA Manager')
    original=Path.read_text
    def read(path,*args,**kw):
        if str(path)=='/sys/class/fpga_manager/fpga0/state':return 'operating'
        return original(path,*args,**kw)
    monkeypatch.setattr(Path,'read_text',read)
    with pytest.raises(s.Stop,match='load not observed'):a._program('base.bin')

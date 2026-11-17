#!/usr/bin/env python3
"""Offline loading benchmark tests. No HTTP, SSH, DUT or deployment."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import plasma_programming_load as b
import plasma_development_dispatch as dispatch

WO='f'*64
CLAIMED={'PLASMA_P2HW_CLAIM_REF':b.CLAIM_PREFIX+WO}


def proc(pid=1,start=10,ticks=0,site=1):
    return dict(pid=pid,starttime=start,ticks=ticks,site=site,ppid=7,rss_kib=100,cpu_pct_one_core=50)


def frame(i,sites=(),cpu=10):
    return dict(frame=i,monotonic_s=i/4,utc='2026-11-17T00:00:00+00:00',errors=[],
                processes=[proc(pid=s,site=s) for s in sites],host_cpu_pct_all_cores=cpu,
                mem_total_kib=1000,mem_available_kib=800,observer_cpu_pct_one_core=2,
                observer_rss_kib=30,scan_duration_s=.01,missed_samples=0)


def schema_check(test,report):
    """Offline subset of the versioned contract (no third-party validator)."""
    import re
    schema=json.loads((ROOT/'specs/programming-loading-benchmark-v1.schema.json').read_text())
    props=schema['properties']
    test.assertTrue(set(schema['required'])<=report.keys())
    test.assertIn(report['outcome'],props['outcome']['enum'])
    for name in ('hardware_trace','measurement_trace'):
        test.assertTrue(set(props[name]['required'])<=report[name].keys())
        for key,rule in props[name]['properties'].items():
            if 'enum' in rule:test.assertIn(report[name][key],rule['enum'],key)
    for site in report['hardware_trace']['sites']:
        test.assertIn(site['result'],['PASS','FAIL'])
    if report['outcome']=='PASS':
        then=schema['allOf'][0]['then']
        test.assertTrue(set(then['required'])<=report.keys())
        test.assertRegex(report['hardware_claim_ref'],props['hardware_claim_ref']['pattern'])
        test.assertEqual(report['hardware_trace']['submission'],'ACCEPTED')
        test.assertEqual(report['measurement_trace']['measurement_outcome'],'OBSERVED')


class Arithmetic(unittest.TestCase):
    def test_stat_parentheses_and_pid_reuse(self):
        fields=['S','7']+['0']*9+['40','60']+['0']*6+['123']+['0']*4
        p=b.stat_parse('42 (a tricky ) name) '+' '.join(fields))
        self.assertEqual(p,dict(pid=42,ppid=7,ticks=100,starttime=123))
        self.assertEqual(b.cpu_percent(proc(ticks=10),proc(ticks=35),.25,100),100)
        self.assertIsNone(b.cpu_percent(proc(),proc(start=11),1,100))
        self.assertIsNone(b.cpu_percent(None,proc(),1,100))
        self.assertIsNone(b.cpu_percent(proc(ticks=10),proc(ticks=0),1,100))
        self.assertEqual(b.host_cpu('cpu 10 0 10 80 0 0 0 0 10 0\n'),(100,80))
        self.assertEqual(b.stats(range(1,21)),dict(n=20,mean=10.5,p95=19,peak=20))
        self.assertIsNone(b.stats([])['p95'])

    def test_mapping_exit_and_dual(self):
        cmd=b'openocd\0-c\0adapter driver plasma_swd\0-c\0plasma_swd site 2\0'
        self.assertEqual(b.site_parse(cmd),2)
        self.assertIsNone(b.site_parse(cmd+b'-c\0plasma_swd site 1\0'))
        self.assertIsNone(b.site_parse(cmd.replace(b'plasma_swd',b'remote_bitbang')))
        self.assertEqual(b.transitions({(1,10):proc()},{}),[dict(event='NO_LONGER_OBSERVED',pid=1,starttime=10)])
        self.assertTrue(b.dual([proc(),proc(pid=2,site=2)]))

    def test_phases_same_baseline_delta_and_overlap(self):
        frames=[frame(i,() if i<64 or i>=90 else (1,) if i<70 else (1,2),
                      10 if i<64 else 50) for i in range(155)]
        r=b.comparison(frames,16,22,22.5,.25)
        self.assertGreaterEqual(r['phases']['idle']['duration_s'],15)
        self.assertGreaterEqual(r['phases']['recovery']['duration_s'],15)
        self.assertEqual(r['phases']['dual_site']['cpu_delta_pp']['mean'],40)
        self.assertEqual(r['sampled_pid_overlap_s'],4.75)
        self.assertEqual(len(r['pids']),2)
        self.assertEqual(b.comparison([],0,0,0,.25)['overlap_status'],'NOT_OBSERVED')
        r=b.comparison([frame(0),frame(1,(1,2))],.1,1,2,.25)
        self.assertEqual(r['phases']['dual_site']['quality'],'INSUFFICIENT_SAMPLES')
        self.assertEqual(r['sampled_pid_overlap_s'],0)

    def test_reused_pid_does_not_bridge_overlap(self):
        a,c=frame(0,(1,2)),frame(1,(1,2))
        c['processes'][0]['starttime']=99
        self.assertEqual(b.comparison([a,c],0,1,2,.25)['sampled_pid_overlap_s'],0)


class Submission(unittest.TestCase):
    def setUp(self):
        self.body={'start_id':'a'*32}
        self.batch=dict(batch_id='b'*32,start_id='a'*32,targets=[{'ppu_alias':'z2','site_ids':[1,2]}])

    def test_one_post_and_duplicate_denied(self):
        client=Mock();client.request.return_value={'batch':self.batch}
        journal={};save=Mock()
        self.assertEqual(b.submit_once(client,self.body,journal,save),'b'*32)
        with self.assertRaisesRegex(b.Blocked,'DUPLICATE'):
            b.submit_once(client,self.body,journal,save)
        self.assertEqual(client.request.call_count,1)
        self.assertEqual(journal['batch_post_count'],1)

    def test_lost_response_reconciles_supported_exact_id(self):
        client=Mock();client.request.side_effect=[TimeoutError(),{'reconciliation':dict(
            start_id='a'*32,state='ACCEPTED_RUNNING',batch=self.batch)}]
        self.assertEqual(b.submit_once(client,self.body,{},lambda:None),'b'*32)
        self.assertEqual([c.args[0] for c in client.request.call_args_list],['POST','GET'])
        self.assertEqual(client.request.call_args.args[1],'/api/programming/starts/'+'a'*32)

    def test_unknown_and_not_accepted_never_retry(self):
        for state in ('OUTCOME_UNKNOWN','NOT_ACCEPTED'):
            client=Mock();client.request.side_effect=[TimeoutError(),{'reconciliation':dict(start_id='a'*32,state=state)}]
            with self.assertRaisesRegex(b.Blocked,'NO_RESEND'):
                b.submit_once(client,self.body,{},lambda:None)
            self.assertEqual([c.args[0] for c in client.request.call_args_list],['POST','GET'])

    def rec(self,state,batch=None):
        return {'reconciliation':dict(start_id='a'*32,state=state,batch=batch)}

    def test_pending_start_is_voided_never_resent(self):
        client=Mock();journal={}
        client.request.side_effect=[TimeoutError(),self.rec('ACCEPTANCE_PENDING'),
                                    self.rec('NOT_ACCEPTED'),self.rec('NOT_ACCEPTED')]
        with self.assertRaisesRegex(b.Blocked,'SUBMISSION_NOT_ACCEPTED_NO_RESEND'):
            b.submit_once(client,self.body,journal,lambda:None)
        calls=[c.args[:2] for c in client.request.call_args_list]
        self.assertEqual(calls,[('POST','/api/programming/batches'),('GET','/api/programming/starts/'+'a'*32),
                                ('POST','/api/programming/starts/'+'a'*32+'/void'),('GET','/api/programming/starts/'+'a'*32)])
        self.assertEqual(client.request.call_args_list[2].args[2],{'void':'VOID_UNSTARTED_START'})
        self.assertEqual((journal['submission'],journal['void_post_count']),('NOT_ACCEPTED',1))

    def test_refused_void_tracks_the_admitted_batch(self):
        client=Mock()
        client.request.side_effect=[TimeoutError(),self.rec('ACCEPTANCE_PENDING'),
                                    b.Blocked('HTTP_REQUEST_REJECTED'),self.rec('ACCEPTED_RUNNING',self.batch)]
        journal={}
        self.assertEqual(b.submit_once(client,self.body,journal,lambda:None),'b'*32)
        self.assertEqual(journal['submission'],'ACCEPTED')
        self.assertEqual([c.args[1] for c in client.request.call_args_list].count('/api/programming/batches'),1)

    def test_still_pending_after_void_stays_unknown(self):
        client=Mock()
        client.request.side_effect=[TimeoutError(),self.rec('ACCEPTANCE_PENDING'),
                                    TimeoutError(),self.rec('ACCEPTANCE_PENDING')]
        journal={}
        with self.assertRaisesRegex(b.Blocked,'SUBMISSION_UNKNOWN_NO_RESEND'):
            b.submit_once(client,self.body,journal,lambda:None)
        self.assertEqual(journal['submission'],'UNKNOWN')
        self.assertEqual(client.request.call_count,4)

    def test_batch_post_has_admission_bound(self):
        seen=[]
        class Conn:
            def __init__(self,host,port,timeout):seen.append(timeout)
            def request(self,*a,**k):pass
            def getresponse(self):
                r=Mock();r.status=200;r.read.return_value=b'{"ok":true}';return r
            def close(self):pass
        client=b.HTTP('http://127.0.0.1:18280');client.deadline=b.time.monotonic()+100
        with patch.object(b.http.client,'HTTPConnection',Conn):
            client.request('POST','/api/programming/batches',{})
            client.request('POST','/api/programming/starts',{})
        self.assertEqual(seen[0],30);self.assertEqual(seen[1],10)

    def test_journal_saved_before_post(self):
        journal={}
        def request(*args):
            self.assertEqual(journal['outcome'],'OUTCOME_UNKNOWN')
            self.assertEqual(saved[-1]['batch_post_count'],1)
            return {'batch':self.batch}
        saved=[];client=Mock();client.request.side_effect=request
        b.submit_once(client,self.body,journal,lambda:saved.append(dict(journal)))


class Guards(unittest.TestCase):
    def test_no_explicit_flag_has_no_io_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'evidence'
            args=argparse.Namespace(output=str(output),timeout_sec=180,run_batch=False)
            client=Mock();remote=Mock();auth=Mock()
            report=b.measure(args,[],client=client,remote=remote,authenticate=auth)
            self.assertEqual(report['outcome'],'NOT_RUN');auth.assert_not_called()
            client.request.assert_not_called();remote.launch.assert_not_called()
            for line in (output/'SHA256SUMS').read_text().splitlines():
                sha,name=line.split('  ');self.assertEqual(sha,b.digest((output/name).read_bytes()))
            with self.assertRaisesRegex(b.Blocked,'OUTPUT_NOT_EMPTY'):
                b.measure(args,[],authenticate=auth)

    def test_cli_bounds_and_stdout(self):
        for argv in (['measure','--sites','1'],['measure','--baseline-sec','1'],
                     ['measure','--timeout-sec','1801'],['measure','--run-batch']):
            with self.assertRaises(SystemExit):b.main(argv)
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/plasma_programming_load.py'),
                       'measure','--output',tmp+'/out'],capture_output=True)
            self.assertEqual(result.returncode,69)
            self.assertLess(len(result.stdout),65536)
            self.assertEqual(json.loads(result.stdout)['outcome'],'NOT_RUN')

    def test_existing_path2_generic_admission(self):
        spec=importlib.util.spec_from_file_location('operator_tests',ROOT/'scripts/tests/test_plasma_path2_operator_cli.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        task,approved=m.admitted(m.work_order(script='scripts/plasma_programming_load.py',
            argv=['measure','--ppu','z2','--sites','1,2'],timeout_seconds=1800))
        self.assertEqual(task['capability'],'operator-cli')
        self.assertEqual(approved['execution_path'],'path2-cli')

    def test_dispatcher_executes_real_no_flash_entrypoint(self):
        spec=importlib.util.spec_from_file_location('operator_tests',ROOT/'scripts/tests/test_plasma_path2_operator_cli.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as tmp:
            task,approval=m.admitted(m.work_order(script='scripts/plasma_programming_load.py',
                argv=['measure','--output',tmp+'/out']))
            # Real child CLI; trusted admission uses fixtures. No Manager or SSH.
            with self.assertRaisesRegex(dispatch.Denied,'OPERATOR_CLI_NOT_RUN_RESOURCE_UNAVAILABLE'):
                dispatch.run_task(task,workspace=ROOT,approval=approval,
                                  evidence_dir=Path(tmp),sandbox=False)
            receipt=json.loads((Path(tmp)/'plasma-path2-process.json').read_text())
            self.assertEqual(receipt['exit_code'],69)
            report=json.loads((Path(tmp)/'out/report.json').read_text())
            self.assertEqual(report['blocker'],'EXPLICIT_RUN_BATCH_REQUIRED')
            self.assertEqual((report['batch_post_count'],report['start_post_count']),(0,0))
            self.assertEqual(report['hardware'],'NOT_RUN')
            schema=json.loads((ROOT/'specs/programming-loading-benchmark-v1.schema.json').read_text())
            self.assertTrue(set(schema['required']) <= report.keys())
            self.assertIn(report['outcome'],schema['properties']['outcome']['enum'])
            self.assertEqual(report['schema'],schema['properties']['schema']['const'])

    def test_run_batch_requires_cross_run_claim_before_io(self):
        for env in ({},{'PLASMA_P2HW_CLAIM_REF':b.CLAIM_PREFIX+'e'*64},{'PLASMA_P2HW_CLAIM_REF':'refs/heads/x'}):
            with tempfile.TemporaryDirectory() as tmp:
                args=argparse.Namespace(output=tmp+'/out',timeout_sec=180,run_batch=True,
                                        config=tmp+'/absent',config_sha256='0'*64)
                client=Mock();remote=Mock()
                clean={k:v for k,v in os.environ.items() if k!='PLASMA_P2HW_CLAIM_REF'}
                with patch.dict(os.environ,{**clean,**env},clear=True):
                    r=b.measure(args,[],client=client,remote=remote,authenticate=lambda argv:{'work_order_sha256':WO})
                self.assertEqual((r['outcome'],r['blocker']),('NOT_RUN','HARDWARE_CLAIM_REQUIRED'))
                self.assertEqual((r['start_post_count'],r['batch_post_count']),(0,0))
                self.assertEqual(r['hardware_trace']['submission'],'NOT_SUBMITTED')
                self.assertEqual(r['measurement_trace']['measurement_outcome'],'NOT_STARTED')
                client.request.assert_not_called();remote.launch.assert_not_called()

    def test_workflow_rerun_cannot_replay_hardware(self):
        env={'GITHUB_RUN_ATTEMPT':'2','RUNNER_NAME':dispatch.EXPECTED_RUNNER,'RUNNER_ENVIRONMENT':'self-hosted'}
        with patch.dict(os.environ,env),patch.object(dispatch,'parse_json') as parsed:
            with self.assertRaisesRegex(b.Blocked,'RUN_ATTEMPT_REPLAY_DENIED'):
                b.authorization(['measure','--run-batch'])
            parsed.assert_not_called()

    def test_workflow_artifact_contract(self):
        workflow=(ROOT/'.github/workflows/plasma-engineering-runtime-dispatch.yml').read_text()
        for name in ('plasma-path2-loading-benchmark.tar.gz','plasma-path2-loading-benchmark.tar.gz.sha256'):
            self.assertIn('${{ runner.temp }}/'+name,workflow)
        self.assertIn('python3 scripts/tests/test_plasma_programming_load.py',workflow)

    def test_phase_boundaries_exclude_unrelated_processes(self):
        result=b.comparison([frame(0,(1,2)),frame(1,(1,)),frame(2),frame(3,(1,2))],.5,.6,.7,.25)
        self.assertEqual(result['phases']['dual_site']['n'],0)
        self.assertEqual(result['phases']['single_site']['n'],0)
        outside=[frame(i,(1,2)) for i in range(4)]
        self.assertEqual(b.comparison(outside,.5,.6,.7,.25)['sampled_pid_overlap_s'],0)

    def test_late_exception_preserves_unknown_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'out'
            def fail(*args):
                output.mkdir()
                b.atomic_json(output/'report.json',dict(batch_post_count=1,source_sha='a'*40))
                raise OSError()
            with patch.object(b,'measure',side_effect=fail),patch('builtins.print') as printed:
                self.assertEqual(b.main(['measure','--output',str(output)]),1)
            self.assertEqual(json.loads(printed.call_args.args[0])['outcome'],'OUTCOME_UNKNOWN')

    def test_sampler_signal_cleanup_real_proc(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)/'samples'
            child=subprocess.Popen([sys.executable,str(ROOT/'scripts/plasma_programming_load.py'),
                      'sample','--duration','2','--output',str(prefix)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            import time
            for _ in range(100):
                if Path(str(prefix)+'.ready.json').exists():break
                time.sleep(.02)
            child.send_signal(signal.SIGTERM)
            stdout,stderr=child.communicate(timeout=5)
            self.assertEqual(child.returncode,0,stderr)
            r=json.loads(Path(str(prefix)+'.json').read_text())
            self.assertEqual(r['termination'],'SIGNAL')
            self.assertGreaterEqual(len(r['frames']),1)


class BoundaryGuards(unittest.TestCase):
    def config(self):
        return dict(profile='bluepill',route_id='route',image_sha256='a'*64,
                    asset_set_sha256='b'*64,resource_set_sha256='c'*64,generation=25,
                    fpga_image_id='v5')

    def plan(self):
        c=self.config()
        return dict(activation_required=False,fpga_load=False,
            resource=dict(reuse=True,ppu_reported=dict(state='VERIFIED',
              asset_set_sha256=c['asset_set_sha256'],resource_set_sha256=c['resource_set_sha256'],generation=25)),
            image_asset=dict(sha256='a'*64,size=2),
            job_binding=dict(site_id=1,icpn=b.TARGET,ppu_id='z2-hil',operations=b.OPERATIONS,
              profile='bluepill',resource_set_sha256='c'*64),
            route=dict(route_id='route',driver_abi='plasma_swd:5',transport='fpga',site_interface='openocd'))

    def test_plan_target_image_profile_resource_negative(self):
        b.check_plan(self.plan(),self.config(),1,b'ab')
        for section,key,value in [('job_binding','icpn','other'),('job_binding','site_id',2),
            ('job_binding','profile','other'),('image_asset','sha256','d'*64),
            ('route','driver_abi','plasma_swd:4'),('resource','reuse',False)]:
            p=self.plan();p[section][key]=value
            with self.assertRaises(b.Blocked):b.check_plan(p,self.config(),1,b'ab')

    def test_seal_busy_and_concurrency(self):
        good=dict(metadata=dict(openocd_pids=[],engine=dict(status='VERIFIED',driver='plasma_swd',abi=5),
             fpga=dict(status='IMAGE',boot_match=True,manager_state='operating',image_id='v5'),
             services={n:dict(ActiveState='active') for n in ('plasma-server','plasma-site-worker','plasma-bootstrap')}),
             config=dict(ppu=dict(id='z2-hil'),server=dict(max_concurrent_jobs=2),
             sites=[dict(id=s,enabled=True,target=b.TARGET,interface='openocd') for s in (1,2)]),
             seals=[],admissions=[])
        b.check_remote(good,self.config())
        for field in ('seals','admissions'):
            changed=copy.deepcopy(good);changed[field]=['present']
            with self.assertRaises(b.Blocked):b.check_remote(changed,self.config())
        changed=copy.deepcopy(good);changed['config']['server']['max_concurrent_jobs']=1
        with self.assertRaises(b.Blocked):b.check_remote(changed,self.config())
        changed=copy.deepcopy(good);changed['metadata']['fpga']['boot_match']=False
        with self.assertRaises(b.Blocked):b.check_remote(changed,self.config())

    def job(self):
        return dict(site_id=1,operation='programming',state='success',attempt=1,job_id='job-1',
             result=dict(attempts=1,image_sha256='a'*64,image_size=2,elapsed_ms=1000,
             details=dict(programming=dict(site=1,operations=b.OPERATIONS,safe_off=True,openocd_rc=0,
             steps=dict(verify=dict(readback_sha256='a'*64))))))

    def test_partial_site_failure_and_safe_off_readback(self):
        self.assertEqual(b.check_job(self.job(),1,self.config())['result'],'PASS')
        j=self.job();j['state']='error'
        with self.assertRaises(b.Blocked):b.check_job(j,1,self.config())
        for key,value in [('safe_off',False),('openocd_rc',1)]:
            j=self.job();j['result']['details']['programming'][key]=value
            with self.assertRaises(b.Blocked):b.check_job(j,1,self.config())

    def test_controller_signal_stops_before_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'image';image.write_bytes(b'ab')
            cfg={**self.config(), 'image':str(image),'image_sha256':b.digest(b'ab'),
                 'image_filename':'image.bin','fixture':['A'*12,'B'*12],
                 'z2_python':'/opt/plasma/python/3.12.13/bin/python3','manager':'http://127.0.0.1:18280'}
            config=Path(tmp)/'config';config.write_text(json.dumps(cfg))
            args=argparse.Namespace(output=tmp+'/out',timeout_sec=180,run_batch=True,
                  config=str(config),config_sha256=b.digest(config.read_bytes()))
            client=Mock();remote=Mock()
            def register(sig,handler):
                if sig == signal.SIGTERM and callable(handler):handler(sig,None)
                return signal.SIG_DFL
            with patch.dict(os.environ,CLAIMED),patch.object(b,'fixture_observation',return_value=[]),patch.object(b.signal,'signal',side_effect=register):
                result=b.measure(args,[],client=client,remote=remote,authenticate=lambda argv:{'work_order_sha256':WO})
            self.assertEqual(result['blocker'],'INTERRUPTED')
            client.request.assert_not_called();remote.launch.assert_not_called()

    def test_timeout_and_bad_config_stop_before_io(self):
        for reason in ('BENCHMARK_TIMEOUT',):
            with tempfile.TemporaryDirectory() as tmp:
                image=Path(tmp)/'image';image.write_bytes(b'ab')
                cfg={**self.config(), 'image':str(image),'image_sha256':b.digest(b'ab'),
                     'image_filename':'image.bin','fixture':['A'*12,'B'*12],
                     'z2_python':'/opt/plasma/python/3.12.13/bin/python3','manager':'http://127.0.0.1:18280'}
                config=Path(tmp)/'config';config.write_text(json.dumps(cfg))
                args=argparse.Namespace(output=tmp+'/out',timeout_sec=180,run_batch=True,
                      config=str(config),config_sha256=b.digest(config.read_bytes()))
                remote=Mock();client=Mock()
                # Raise at the first bounded API operation; no POST can occur.
                with patch.dict(os.environ,CLAIMED),patch.object(b,'fixture_observation',return_value=[]),patch.object(b.time,'monotonic',side_effect=[0,181]):
                    r=b.measure(args,[],client=client,remote=remote,authenticate=lambda argv:{'work_order_sha256':WO})
                self.assertEqual(r['outcome'],'NOT_RUN');self.assertEqual(r['blocker'],'BENCHMARK_TIMEOUT')
                client.request.assert_not_called();remote.launch.assert_not_called()


class EndToEnd(unittest.TestCase):
    def test_one_batch_same_sampler_baselines_and_partial_failure(self):
        for mode in ('pass','partial','packaging','claimed','collect','startlost'):
            partial,packaging_failure=mode=='partial',mode=='packaging'
            with tempfile.TemporaryDirectory() as tmp:
                checks=BoundaryGuards();cfg=checks.config()
                image=Path(tmp)/'image';image.write_bytes(b'ab')
                cfg.update(image=str(image),image_filename='image.bin',image_sha256=b.digest(b'ab'),
                    fixture=['A'*12,'B'*12],z2_python='/opt/plasma/python/3.12.13/bin/python3',
                    manager='http://127.0.0.1:18280',device_id='device',deployed_sha='d'*40)
                config=Path(tmp)/'cfg';config.write_text(json.dumps(cfg))
                args=argparse.Namespace(output=tmp+'/out',timeout_sec=180,run_batch=True,config=str(config),
                    config_sha256=b.digest(config.read_bytes()),baseline_sec=15,recovery_sec=15,interval_ms=1000)
                status=dict(ppu=dict(ppu_id='z2-hil',execution=dict(busy=False,active_job_count=0),
                            runtime_activation=dict(active=False)),sites=[dict(site_id=s,enabled=True,
                            interface='openocd',state='idle',current_job_id=None,queued_jobs=0) for s in (1,2)])
                batch=dict(batch_id='b'*32,start_id='a'*32,targets=[dict(ppu_alias='z2',site_ids=[1,2])],
                           units=[dict(site_id=s,attempts=[dict(job_id='job-'+str(s))]) for s in (1,2)])
                class Client:
                    submitted=False
                    done=False
                    polls=0
                    posts=[]
                    def request(self,method,path,body=None):
                        if method=='POST':
                            self.posts.append(path)
                            if path.endswith('/plans'):return {'plan':checks.plan()}
                            if path.endswith('/starts'):
                                if mode=='startlost':raise TimeoutError()
                                return {'start':{'start_id':'a'*32}}
                            if path.endswith('/batches'):
                                self.submitted=True;return {'batch':batch}
                        if path.endswith('/bootstrap'):return dict(pairing=dict(device_authenticated=True,device_id='device'),
                              bootstrap=dict(runtime=dict(git_sha='d'*40)))
                        if '?job=' in path:
                            j=checks.job();site=int(path[-1]);j['site_id']=site;j['job_id']='job-'+str(site)
                            j['result']['image_sha256']=cfg['image_sha256']
                            pr=j['result']['details']['programming'];pr['site']=site
                            pr['steps']['verify']['readback_sha256']=cfg['image_sha256']
                            if partial and site==2:j['state']='error'
                            return {'job':j}
                        if path.endswith('/status'):return copy.deepcopy(status)
                        if '/starts/' in path:return {'reconciliation':dict(state='TERMINAL_CONFIRMED',batch=batch)}
                        if '/batches/' in path:
                            self.polls+=1;self.done=self.polls>=4
                            return {'batch':{**batch,'outcome':('PARTIAL' if partial else 'PASS') if self.done else None}}
                        raise AssertionError((method,path))
                client=Client()
                class Remote:
                    t=-1
                    frames=[]
                    stopped=False
                    def launch(self,*args):return {'source_sha256':'test'}
                    def inspect(self):return {'metadata':{'fpga':{}}}
                    def status(self,observer,stop=False):
                        if stop:self.stopped=True
                        if not self.stopped:
                            self.t+=1
                            f=frame(self.t,(1,2) if client.submitted and not client.done else ())
                            f['monotonic_s']=self.t;self.frames.append(f)
                        return dict(ready=self.frames[0],latest=self.frames[-1],alive=True,finished=self.stopped)
                    def remove(self,*args):return {'ephemeral_removed':True}
                    def collect(self,*args):
                        if mode=='collect':raise OSError()
                        return dict(frames=self.frames,termination='SIGNAL',observer_average_cpu_pct_one_core=1)
                remote=Remote();remote.frames=[]
                if packaging_failure:
                    (Path(tmp)/'plasma-path2-loading-benchmark.tar.gz.sha256').write_text('existing')
                if mode=='claimed':
                    (Path(tmp)/('plasma-loading-'+'f'*64+'.claim')).write_text('{}')
                class Event:
                    def wait(self,*a):pass
                    def is_set(self):return False
                    def set(self):pass
                with patch.dict(os.environ,{'RUNNER_TEMP':tmp,**CLAIMED}),patch.object(b,'fixture_observation',return_value=[]),patch.object(b,'check_remote'), \
                     patch.object(b,'check_plan'),patch.object(b.threading,'Event',Event):
                    result=b.measure(args,[],client=client,remote=remote,authenticate=lambda argv:{'work_order_sha256':'f'*64,'source_sha':'d'*40,
                         'execution_path':'path2-cli','dispatcher_timeout_seconds':300})
                hw,ms=result['hardware_trace'],result['measurement_trace']
                if mode=='startlost':
                    # Lost Start response: no Batch POST, recorded as UNKNOWN issuance.
                    self.assertEqual((result['outcome'],hw['start_issuance'],hw['submission']),('NOT_RUN','UNKNOWN','NOT_SUBMITTED'))
                    self.assertNotIn('/api/programming/batches',client.posts)
                    continue
                if mode=='claimed':
                    self.assertEqual((hw['submission'],ms['measurement_outcome']),('NOT_SUBMITTED','NOT_STARTED'))
                    # Claim precedes every Z2 observer and Start side effect.
                    self.assertEqual((result['outcome'],result['blocker']),('NOT_RUN','FileExistsError'))
                    self.assertFalse([x for x in client.posts if x.endswith(('/starts','/batches'))])
                    self.assertEqual(remote.frames,[])
                    continue
                if mode=='collect':
                    # Lost sampler evidence never turns a known Batch into UNKNOWN.
                    self.assertEqual((result['outcome'],result['batch_outcome'],result['cleanup']),('FAIL','PASS','OSError'))
                    self.assertEqual((hw['submission'],hw['batch_outcome'],ms['measurement_outcome']),('ACCEPTED','PASS','FAILED'))
                    self.assertEqual([x['result'] for x in hw['sites']],['PASS','PASS'])
                    self.assertEqual(client.posts.count('/api/programming/batches'),1)
                    continue
                self.assertEqual(result['outcome'],'FAIL' if partial or packaging_failure else 'PASS',result.get('blocker'))
                self.assertEqual((hw['start_issuance'],hw['submission'],hw['batch_id']),('ISSUED','ACCEPTED','b'*32))
                # A failed Site never hides the other Site's physical result.
                self.assertEqual([(x['site_id'],x['result']) for x in hw['sites']],
                                 [(1,'PASS'),(2,'FAIL' if partial else 'PASS')])
                self.assertEqual(ms['measurement_outcome'],'OBSERVED')
                self.assertEqual(result['hardware_claim_ref'],b.CLAIM_PREFIX+WO)
                schema_check(self,result)
                self.assertEqual(client.posts.count('/api/programming/batches'),1)
                self.assertTrue(remote.stopped)
                artifact=Path(tmp)/'plasma-path2-loading-benchmark.tar.gz'
                if packaging_failure:
                    self.assertFalse(artifact.exists())
                    self.assertEqual(artifact.with_suffix('.gz.sha256').read_text(),'existing')
                    continue
                self.assertTrue(artifact.is_file())
                self.assertEqual(artifact.with_suffix('.gz.sha256').read_text().split()[0],b.digest(artifact.read_bytes()))
                import tarfile
                with tarfile.open(artifact) as packed:
                    self.assertIn('report.json',packed.getnames())
                    self.assertIn('SHA256SUMS',packed.getnames())
                    self.assertIn('phases.csv',packed.getnames())
                    self.assertEqual(json.loads(packed.extractfile('report.json').read()),result)
                    for line in packed.extractfile('SHA256SUMS').read().decode().splitlines():
                        sha,name=line.split('  ')
                        self.assertEqual(sha,b.digest(packed.extractfile(name).read()))
                self.assertTrue(result['final_idle'])
                self.assertGreaterEqual(result['comparison']['phases']['idle']['duration_s'],15)
                self.assertGreaterEqual(result['comparison']['phases']['recovery']['duration_s'],15)
                self.assertGreater(result['comparison']['sampled_pid_overlap_s'],0)


if __name__=='__main__':unittest.main()


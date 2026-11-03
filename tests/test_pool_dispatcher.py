"""Independent external-boundary witnesses from frozen ORACLE.v1, not model expectations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
TEMP_ROOT=ROOT/'metadata' if (ROOT/'metadata').is_dir() else None
for p in (ROOT/'metadata/input', ROOT/'metadata/input-lane02', ROOT/'scripts'):
    sys.path.insert(0,str(p))

FAKE=r'''
import argparse,datetime,json,os,pathlib,sys,time
p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('task')
for name in ('output','config','machine-id','owner','stop-file'):p.add_argument('--'+name,required=True)
a=p.parse_args();cfg=json.loads(pathlib.Path(a.spec).read_text());out=pathlib.Path(a.output);out.mkdir(exist_ok=True)
fd=os.open(cfg['marker'],os.O_CREAT|os.O_APPEND|os.O_WRONLY|getattr(os,'O_BINARY',0),0o600);os.write(fd,b'L\n');os.close(fd)
with (out/'DISPATCH.claim').open('x') as f:f.write('caller-owned')
time.sleep(0.03)
def event(name,**extra):
 row=dict(event=name,attempt=1,task_id=a.task,machine_id=a.machine_id,owner=a.owner,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**extra)
 with (out/'EVENTS.jsonl').open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(row)+'\n')
mode=cfg['mode']
if mode=='cancel':event('CANCELLED_BEFORE_POST');sys.exit(1)
event('POST_BEGIN',network_routing={'proxy_mode':'direct'})
if mode=='unpaired':sys.exit(2)
event('ATTEMPT_END',post_invoked=True,finish_reason='stop',sse_done=True,candidate_complete=False,total_ms=1)
if mode=='backoff':event('RETRY_BACKOFF',delay_seconds=1)
sys.exit(1)
'''

def dispatcher(base, cls=None, **overrides):
    from pool_dispatcher import Dispatcher
    options=dict(capacity=2,reserve_runtime=1,max_records=100,ttl=60)
    options.update(overrides)
    return (cls or Dispatcher)(base/'dispatch.db',base/'leases.db',python_executable=Path(sys.executable).resolve(),caller_path=base/'fake.py',stop_file=base/'STOP',**options)

def queue(base):
    return json.loads((base/'queue.json').read_text())

def settle(d, seconds=1.0):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        d.tick([])
        time.sleep(0.01)

def fixture(base,mode='paired'):
    (base/'fake.py').write_text(FAKE)
    (base/'config.json').write_text('{}')
    (base/'spec.json').write_text(json.dumps({'mode':mode,'marker':str(base/'marker')}))
    record={'id':'id1','owner':'ownerA','spec_path':str(base/'spec.json'),'task_id':'task1','output_path':str(base/'out'),'config_path':str(base/'config.json'),'machine_id':'fixture','lane':'source'}
    (base/'queue.json').write_text(json.dumps([record]))
    return record

def launches(base):
    return (base/'marker').read_bytes().count(b'L\n') if (base/'marker').exists() else 0

class Counter(unittest.TestCase):
    def test_P01_two_real_processes_launch_one_logical_task_once(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-counter-',dir=TEMP_ROOT) as td:
            base=Path(td);fixture(base);owned=[]
            try:
                for i in range(2):
                    owned.append(subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',str(base),str(i)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,shell=False))
                deadline=time.monotonic()+4
                while not all((base/('ready'+str(i))).exists() for i in range(2)):
                    self.assertLess(time.monotonic(),deadline,'workers must enter before releasing the common barrier')
                    time.sleep(0.01)
                (base/'GO').write_text('go')
                for child in owned:
                    _,error=child.communicate(timeout=5)
                    self.assertEqual(child.returncode,0,error.decode(errors='replace'))
                self.assertEqual(launches(base),1)
            finally:
                for child in owned:
                    if child.poll() is None:child.kill();child.wait(timeout=2)

    def test_P14_exit2_unpaired_POST_retains_capacity_and_restart_never_relaunches(self):
        from pool_leases import LeaseStore
        with tempfile.TemporaryDirectory(prefix='dispatcher-counter-',dir=TEMP_ROOT) as td:
            base=Path(td);r=fixture(base,'unpaired');d=dispatcher(base);d.tick([r]);settle(d)
            self.assertEqual(launches(base),1)
            lease=LeaseStore(base/'leases.db',capacity=2,reserve_runtime=1,max_records=100)
            self.assertEqual(lease.snapshot(now=time.time())['occupied'],1)
            restarted=dispatcher(base);restarted.tick([r]);settle(restarted,0.1)
            self.assertEqual(launches(base),1)
            self.assertEqual(lease.snapshot(now=time.time())['occupied'],1)

    def test_P16_authoritative_cancel_before_POST_allows_release(self):
        from pool_leases import LeaseStore
        with tempfile.TemporaryDirectory(prefix='dispatcher-counter-',dir=TEMP_ROOT) as td:
            base=Path(td);r=fixture(base,'cancel');d=dispatcher(base);d.tick([r]);settle(d)
            self.assertEqual(launches(base),1)
            lease=LeaseStore(base/'leases.db',capacity=2,reserve_runtime=1,max_records=100)
            self.assertEqual(lease.snapshot(now=time.time())['occupied'],0)

    def test_P17_process_loss_after_BACKOFF_stays_unknown(self):
        from pool_leases import LeaseStore
        with tempfile.TemporaryDirectory(prefix='dispatcher-counter-',dir=TEMP_ROOT) as td:
            base=Path(td);r=fixture(base,'backoff');d=dispatcher(base);d.tick([r]);settle(d)
            self.assertEqual(launches(base),1)
            lease=LeaseStore(base/'leases.db',capacity=2,reserve_runtime=1,max_records=100)
            self.assertEqual(lease.snapshot(now=time.time())['occupied'],1)

EXTENDED_FAKE=r'''
import argparse,datetime,json,os,pathlib,sys,time
p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('task')
for name in ('output','config','machine-id','owner','stop-file'):p.add_argument('--'+name,required=True)
a=p.parse_args();cfg=json.loads(pathlib.Path(a.spec).read_text());out=pathlib.Path(a.output);out.mkdir(exist_ok=True)
fd=os.open(cfg['marker'],os.O_CREAT|os.O_APPEND|os.O_WRONLY|getattr(os,'O_BINARY',0),0o600);os.write(fd,b'L\n');os.close(fd)
with open(cfg['marker']+'.order','a',encoding='utf-8',newline='\n') as f:f.write(json.dumps({'task':a.task,'owner':a.owner,'argv':sys.argv[1:]})+'\n')
with (out/'DISPATCH.claim').open('x') as f:f.write('caller-owned')
def finish(code):
 (out/'FAKE-DONE').write_text('done');sys.exit(code)
def event(name,**extra):
 row=dict(event=name,attempt=1,task_id=a.task,machine_id=a.machine_id,owner=a.owner+('wrong' if cfg['mode']=='identity' else ''),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**extra)
 with (out/'EVENTS.jsonl').open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(row)+'\n')
mode=cfg['mode']
if mode=='missing':finish(2)
if mode=='partial':(out/'EVENTS.jsonl').write_bytes(b'{');finish(0)
if mode=='retry2':
 for attempt in (1,2):
  now=datetime.datetime.now(datetime.timezone.utc).isoformat()
  rows=[dict(event='POST_BEGIN',attempt=attempt,task_id=a.task,machine_id=a.machine_id,owner=a.owner,at_utc=now),dict(event='ATTEMPT_END',attempt=attempt,task_id=a.task,machine_id=a.machine_id,owner=a.owner,at_utc=now,post_invoked=True)]
  with (out/'EVENTS.jsonl').open('a',encoding='utf-8',newline='\n') as f:
   for row in rows:f.write(json.dumps(row)+'\n')
 finish(1)
event('POST_BEGIN',network_routing={'proxy_mode':'direct'})
if mode=='hold':
 deadline=time.monotonic()+4
 while not pathlib.Path(cfg['release']).exists():
  if time.monotonic()>deadline:finish(2)
  time.sleep(.01)
event('ATTEMPT_END',post_invoked=True,finish_reason='stop',sse_done=True,candidate_complete=False,total_ms=1)
finish(1)
'''

def extended_fixture(base,mode='paired'):
    record=fixture(base,mode)
    (base/'fake.py').write_text(EXTENDED_FAKE)
    (base/'spec.json').write_text(json.dumps({'mode':mode,'marker':str(base/'marker'),'release':str(base/'RELEASE')}))
    return record

def another(record,number,owner=None):
    return {**record,'id':'id'+str(number),'task_id':'task'+str(number),'output_path':str(Path(record['output_path']).parent/('out'+str(number))),**({'owner':owner} if owner else {})}

def wait_for(predicate,seconds=5):
    end=time.monotonic()+seconds
    while not predicate():
        if time.monotonic()>end:raise AssertionError('bounded offline fixture did not reach its actual boundary')
        time.sleep(.01)

class BoundaryTests(unittest.TestCase):
    def test_P02_P03_P04_task_output_and_metadata_remain_immutable(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-boundary-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);d=dispatcher(b);d.run_once([r])
            for changed in ({**r,'id':'other','output_path':str(b/'otherout')},
                            {**another(r,2),'output_path':str(b/'unused'/'..'/'out')},
                            {**r,'owner':'changed'}):
                self.assertTrue(d.tick([changed])['conflict'])
            self.assertEqual(launches(b),1)
            self.assertEqual(d.records()[0]['owner'],'ownerA')

    def test_P05_durable_intent_crash_before_Popen_stays_unknown(self):
        self._crash_case('before',71,0)

    def test_P06_process_loss_after_spawn_never_replays_or_releases(self):
        self._crash_case('after',72,1)

    def _crash_case(self,point,expected_exit,expected_launches):
        with tempfile.TemporaryDirectory(prefix='dispatcher-crash-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b)
            child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--crash',str(b),point],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,shell=False)
            try:
                _,err=child.communicate(timeout=6)
                self.assertEqual(child.returncode,expected_exit,err.decode(errors='replace'))
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=2)
            if expected_launches:wait_for(lambda:(b/'out/FAKE-DONE').exists())
            d=dispatcher(b)
            self.assertEqual(d.records()[0]['state'],'UNKNOWN')
            d.tick([r])
            self.assertEqual(launches(b),expected_launches)
            self.assertEqual(d.lease_snapshot()['occupied'],1)

    def test_P07_Runtime_uses_reserved_position_while_source_waits(self):
        from pool_leases import LeaseStore
        with tempfile.TemporaryDirectory(prefix='dispatcher-reserve-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);d=dispatcher(b)
            leases=LeaseStore(b/'leases.db',capacity=2,reserve_runtime=1,max_records=100)
            self.assertTrue(leases.acquire('existing','external',now=time.time(),ttl=60).newly_acquired)
            runtime={**another(r,2),'lane':'runtime'}
            result=d.run_once([r,runtime])
            self.assertEqual(result['launched'],['id2'])
            self.assertEqual(launches(b),1)
            self.assertEqual(d.lease_snapshot()['occupied_source'],1)

    def test_P08_lease_history_full_is_not_capacity(self):
        from pool_leases import LeaseStore
        with tempfile.TemporaryDirectory(prefix='dispatcher-history-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);d=dispatcher(b,max_records=2);d.run_once([r])
            leases=LeaseStore(b/'leases.db',capacity=2,reserve_runtime=1,max_records=2)
            self.assertTrue(leases.acquire('external','external',now=time.time(),ttl=60).newly_acquired)
            self.assertTrue(leases.release('external','external',verified_no_live_post=True))
            result=d.tick([another(r,2)])
            self.assertTrue(result['lease_history_full'])
            self.assertFalse(result['history_full'])
            self.assertEqual(d.lease_snapshot()['occupied'],0)
            self.assertEqual(launches(b),1)

    def test_P09_one_record_budget_launches_once_and_preserves_tombstone(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-maxone-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);d=dispatcher(b,max_records=1)
            self.assertEqual(d.run_once([r])['launched'],['id1'])
            result=d.tick([another(r,2)])
            self.assertTrue(result['history_full'])
            self.assertEqual(launches(b),1)
            self.assertEqual(d.lease_snapshot()['records'],1)
            self.assertEqual(d.lease_snapshot()['released'],1)

    def test_P10_capacity_deferral_refills_with_the_saved_owner_cursor(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-fair-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);d=dispatcher(b)
            result=d.run_once([r,another(r,2),another(r,3,'ownerB')])
            self.assertEqual(result['launched'],['id1','id3','id2'])
            self.assertEqual(launches(b),3)
            restarted=dispatcher(b)
            newer=another(r,4,'ownerB');last=another(r,5)
            self.assertEqual(restarted.run_once([last,newer])['launched'],['id4','id5'])

    def test_P11_P12_stop_before_tick_and_after_claim_launches_no_child(self):
        from pool_dispatcher import Dispatcher
        class StopAfterClaim(Dispatcher):
            def _claim(self,db,record):
                result=super()._claim(db,record);Path(self.stop_file).write_text('stop');return result
        for after_claim in (False,True):
            with self.subTest(after_claim=after_claim),tempfile.TemporaryDirectory(prefix='dispatcher-stop-',dir=TEMP_ROOT) as td:
                b=Path(td);r=extended_fixture(b)
                if not after_claim:(b/'STOP').write_text('stop')
                d=dispatcher(b,cls=StopAfterClaim if after_claim else None);result=d.tick([r])
                self.assertEqual(launches(b),0)
                self.assertEqual(d.lease_snapshot()['occupied'],0)
                if after_claim:self.assertEqual(result['cancelled_before_launch'],['id1'])

    def test_P13_stop_drains_existing_handle_without_launching_the_next_task(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-live-stop-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b,'hold');d=dispatcher(b);result=[];errors=[]
            def run():
                try:result.append(d.run_once([r,another(r,2)]))
                except BaseException as exc:errors.append(exc)
            thread=threading.Thread(target=run);thread.start()
            try:
                wait_for(lambda:(b/'out/EVENTS.jsonl').exists())
                (b/'STOP').write_text('stop');thread.join(.1)
                self.assertTrue(thread.is_alive(),'stop must not abandon a still-owned in-flight child')
            finally:
                (b/'RELEASE').write_text('finish');thread.join(6)
            self.assertFalse(thread.is_alive());self.assertFalse(errors,errors)
            self.assertEqual(launches(b),1)
            self.assertEqual(d.lease_snapshot()['occupied'],0)

    def test_P18_missing_partial_or_wrong_identity_never_releases(self):
        for mode in ('missing','partial','identity'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='dispatcher-evidence-',dir=TEMP_ROOT) as td:
                b=Path(td);r=extended_fixture(b,mode);d=dispatcher(b);result=d.run_once([r])
                self.assertTrue(result['unknown'])
                self.assertEqual(d.records()[0]['state'],'UNKNOWN')
                self.assertEqual(d.lease_snapshot()['occupied'],1)

    def test_P19_leading_CLI_options_are_rejected_and_shell_text_stays_literal(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-argv-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);d=dispatcher(b)
            self.assertTrue(d.tick([{**r,'task_id':'--help'}])['errors'])
            literal={**r,'task_id':'literal & echo untouched','owner':'owner;literal'}
            d.run_once([literal])
            row=json.loads((b/'marker.order').read_text().splitlines()[0])
            self.assertEqual(row['task'],literal['task_id']);self.assertEqual(row['owner'],literal['owner'])
            self.assertEqual(launches(b),1)

    def test_rolling_file_refresh_adds_new_ready_work_until_explicit_stop(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-refresh-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);(b/'queue.json').write_text('[]');d=dispatcher(b);errors=[]
            def run():
                try:d.run_file(b/'queue.json')
                except BaseException as exc:errors.append(exc)
            thread=threading.Thread(target=run);thread.start()
            try:
                for jobs in ([r],[r,another(r,2)]):
                    temp=b/'queue.next';temp.write_text(json.dumps(jobs));temp.replace(b/'queue.json')
                    wait_for(lambda:launches(b)==len(jobs))
            finally:
                (b/'STOP').write_text('stop');thread.join(6)
            self.assertFalse(thread.is_alive());self.assertFalse(errors,errors)
            self.assertEqual(launches(b),2)

    def test_P20_clean_module_import_cannot_open_DB_or_launch_a_child(self):
        child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--import-only'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False)
        try:
            _,error=child.communicate(timeout=6)
            self.assertEqual(child.returncode,0,error.decode(errors='replace'))
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=2)

    def test_P21_two_reported_attempts_belong_to_one_canonical_CLI(self):
        from pool_observer import observe_stream
        with tempfile.TemporaryDirectory(prefix='dispatcher-retries-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b,'retry2');d=dispatcher(b);d.run_once([r])
            report=observe_stream(b/'out/EVENTS.jsonl')
            self.assertEqual(report['evidence_status'],'KNOWN')
            self.assertEqual(report['observed_POSTs'],2)
            self.assertEqual(report['observed_paired_POST_ENDs'],2)
            self.assertEqual(launches(b),1)
            self.assertEqual(d.lease_snapshot()['occupied'],0)

    def test_P22_preexisting_caller_claim_is_retained_without_launch(self):
        with tempfile.TemporaryDirectory(prefix='dispatcher-existing-',dir=TEMP_ROOT) as td:
            b=Path(td);r=extended_fixture(b);(b/'out').mkdir();claim=b/'out/DISPATCH.claim';claim.write_bytes(b'original-caller')
            d=dispatcher(b);result=d.run_once([r])
            self.assertTrue(result['unknown']);self.assertEqual(launches(b),0)
            self.assertEqual(claim.read_bytes(),b'original-caller')
            self.assertEqual(d.lease_snapshot()['occupied'],1)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--import-only':
        def forbid_import_side_effect(event,args):
            if event in ('sqlite3.connect','subprocess.Popen','socket.__new__','socket.connect'):
                raise AssertionError('module import attempted '+event)
            if event=='import' and args[0] in ('call','check_opencode'):
                raise AssertionError('dispatcher imported the active caller/maintenance')
        sys.addaudithook(forbid_import_side_effect)
        import pool_dispatcher
    elif len(sys.argv)>1 and sys.argv[1]=='--crash':
        import pool_dispatcher as production
        base=Path(sys.argv[2]);point=sys.argv[3]
        if point=='before':
            class Crash(production.Dispatcher):
                def _launch(self,record,summary):os._exit(71)
            d=dispatcher(base,cls=Crash)
        else:
            original=subprocess.Popen
            class ExitAfterSpawn(original):
                def __init__(self,*args,**kwargs):
                    super().__init__(*args,**kwargs);os._exit(72)
            production.subprocess.Popen=ExitAfterSpawn
            d=dispatcher(base)
        d.tick(queue(base));raise AssertionError('actual crash boundary not reached')
    elif len(sys.argv)>1 and sys.argv[1]=='--worker':
        base=Path(sys.argv[2]);index=sys.argv[3];d=dispatcher(base)
        (base/('ready'+index)).write_text('ready')
        limit=time.monotonic()+5
        while not (base/'GO').exists():
            if time.monotonic()>limit:raise RuntimeError('barrier expired')
            time.sleep(0.01)
        d.tick(queue(base));settle(d)
    else:unittest.main()

"""Only new transport-selection behavior; no external or loopback network."""
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout
import copy,importlib.util,io,json,os,tempfile,unittest,urllib.error

ROOT=Path(__file__).resolve().parents[1]
candidate=Path(os.environ.get('LOCAL_MODEL_CALL_CANDIDATE',str(ROOT/'scripts/call.py')))
spec=importlib.util.spec_from_file_location('direct_route_call_candidate',candidate)
CALL=importlib.util.module_from_spec(spec);spec.loader.exec_module(CALL)
CONFIG=Path(os.environ.get('LOCAL_MODEL_TEST_EXECUTOR',str(ROOT/'config/executor.json')))

class Response:
    status=200
    headers={}
    def __enter__(self):return self
    def __exit__(self,*args):return None
    def __iter__(self):
        for chunk in [
            {'choices':[{'delta':{'content':'{"text":"雪"}\n'},'finish_reason':None}]},
            {'choices':[{'delta':{},'finish_reason':'stop'}]},
            {'choices':[],'usage':{'prompt_tokens':3,'completion_tokens':5}}]:
            yield ('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode('utf-8')
        yield b'data: [DONE]\n\n'

class DirectRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=json.loads(CONFIG.read_bytes())
        self.config['network']={'proxy_mode':'direct','direct_host':'192.168.1.11'}
        self.config['transient_retries']['backoff_seconds']=[0]*5
        self.config['transient_retries']['jitter_ratio']=0
        (self.root/'source.txt').write_bytes('line1\r\n雪\n'.encode('utf-8'))
        (self.root/'task.txt').write_bytes(b'Review a real bounded component.')
        self.request=self.root/'spec.json'
        CALL.save_json(self.request,{'source_files':['source.txt'],'task_path':'task.txt','max_tokens':900})

    def dispatch(self,opener):
        with mock.patch.object(CALL.urllib.request,'build_opener',return_value=opener) as factory, \
             mock.patch.object(CALL.urllib.request,'urlopen',side_effect=AssertionError('environment transport forbidden')) as global_open, \
             mock.patch.object(CALL.socket.socket,'connect',side_effect=AssertionError('network forbidden')), \
             mock.patch.dict(os.environ,{'HTTP_PROXY':'http://127.0.0.1:9','HTTPS_PROXY':'http://127.0.0.1:9','NO_PROXY':''}), \
             redirect_stdout(io.StringIO()):
            result=CALL.dispatch(self.request,'direct',self.root/'out',self.config,'fixture','fixture',None)
        return result,factory,global_open

    def test_direct_disables_proxy_preserves_request_and_evidence(self):
        opener=mock.Mock();opener.open.return_value=Response()
        code,factory,global_open=self.dispatch(opener)
        self.assertEqual(0,code);global_open.assert_not_called()
        handlers=factory.call_args.args
        self.assertIsInstance(handlers[0],CALL.urllib.request.ProxyHandler)
        self.assertEqual({},handlers[0].proxies)
        self.assertIsInstance(handlers[1],CALL.NoModelRedirect)
        request=opener.open.call_args.args[0]
        body=json.loads(request.data)
        self.assertEqual(3,len(body['messages']));self.assertIn('line1\n雪\n',body['messages'][1]['content'])
        self.assertNotIn('network',body);self.assertNotIn('priority',body)
        self.assertEqual('{"text":"雪"}\n'.encode(),(self.root/'out/ATTEMPT1-CONTENT.txt').read_bytes())
        result=json.loads((self.root/'out/ATTEMPT1-RESULT.json').read_bytes())
        self.assertEqual('direct',result['network_routing']['proxy_mode'])
        self.assertEqual('UNKNOWN',result['network_routing']['actual_peer'])
        self.assertEqual('VALID',result['json_syntax']['status']);self.assertFalse(result['adopted'])

    def test_wrong_or_unqualified_direct_endpoint_rejected_before_claim(self):
        variants=[{'proxy_mode':'unsupported'}, {'proxy_mode':'direct','direct_host':''},
                  {'proxy_mode':'direct','direct_host':'different.example'},
                  {'proxy_mode':'direct','direct_host':'192.168.1.11 '},None]
        with mock.patch.object(CALL.urllib.request,'build_opener') as factory:
            for index,network in enumerate(variants):
                config=copy.deepcopy(self.config);config['network']=network
                with self.subTest(network=network), self.assertRaises(ValueError):
                    CALL.dispatch(self.request,'invalid',self.root/str(index),config,'fixture','fixture',None)
                self.assertFalse((self.root/str(index)).exists())
            config=copy.deepcopy(self.config);config['base_url']='http://user:secret@192.168.1.11/v1'
            with self.assertRaises(ValueError):CALL.network_transport(config)
        factory.assert_not_called()

    def test_direct_refuses_redirect_instead_of_dialing_other_host(self):
        handler=CALL.NoModelRedirect()
        self.assertIsNone(handler.redirect_request(None,None,302,'',{},'http://different.example/'))
        self.assertIsNone(handler.redirect_request(None,None,307,'',{},'http://192.168.1.11/other'))

    def test_explicit_environment_retains_environment_transport(self):
        config=copy.deepcopy(self.config);config['network']={'proxy_mode':'environment'}
        with mock.patch.object(CALL.urllib.request,'urlopen') as existing, \
             mock.patch.object(CALL.urllib.request,'build_opener') as factory:
            transport,meta=CALL.network_transport(config)
        self.assertIs(existing,transport);factory.assert_not_called()
        self.assertEqual('environment',meta['proxy_mode'])

    def test_transport_retry_uses_same_body_and_same_direct_opener(self):
        opener=mock.Mock();opener.open.side_effect=[urllib.error.URLError('mock reset'),Response()]
        code,factory,global_open=self.dispatch(opener)
        self.assertEqual(0,code);self.assertEqual(2,opener.open.call_count)
        self.assertEqual(1,factory.call_count);global_open.assert_not_called()
        first,second=[x.args[0].data for x in opener.open.call_args_list]
        self.assertEqual(first,second)
        events=[json.loads(x) for x in (self.root/'out/EVENTS.jsonl').read_text().splitlines()]
        self.assertEqual(2,sum(x['event']=='POST_BEGIN' for x in events))
        self.assertEqual(2,sum(x['event']=='ATTEMPT_END' for x in events))
        self.assertEqual(1,sum(x['event']=='RETRY_BACKOFF' for x in events))
        self.assertTrue(all(x['network_routing']['proxy_mode']=='direct' for x in events if x['event']=='POST_BEGIN'))

if __name__=='__main__':unittest.main()

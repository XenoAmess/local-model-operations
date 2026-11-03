"""New default routing contract; zero external or loopback network."""
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout
import copy,importlib.util,io,json,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('new_default_call',ROOT/'scripts/call.py')
CALL=importlib.util.module_from_spec(spec);spec.loader.exec_module(CALL)

class Response:
    status=200
    headers={}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def __iter__(self):
        yield b'data: {"choices":[{"delta":{"content":"{}"},"finish_reason":null}]}\n\n'
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b'data: [DONE]\n\n'

class DefaultDirectTests(unittest.TestCase):
    def config(self):return json.loads((ROOT/'config/executor.json').read_bytes())

    def test_missing_network_dispatch_is_direct_to_configured_host(self):
        config=self.config();config.pop('network',None)
        config['base_url']='https://another-trusted-host.invalid:8443/model'
        before=copy.deepcopy(config)
        opener=mock.Mock();opener.open.return_value=Response()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);request=root/'request.json'
            CALL.save_json(request,{'messages':[{'role':'system','content':'ignored'},{'role':'user','content':'source'},{'role':'user','content':'task'}],'max_tokens':10})
            with mock.patch.object(CALL.urllib.request,'build_opener',return_value=opener) as factory, \
                 mock.patch.object(CALL.urllib.request,'urlopen',side_effect=AssertionError('implicit proxy forbidden')) as implicit, \
                 mock.patch.dict('os.environ',{'HTTP_PROXY':'http://127.0.0.1:9','HTTPS_PROXY':'http://127.0.0.1:9','NO_PROXY':''}), \
                 mock.patch.object(CALL.socket.socket,'connect',side_effect=AssertionError('network forbidden')),redirect_stdout(io.StringIO()):
                code=CALL.dispatch(request,'default-direct',root/'out',config,'fixture','fixture',None)
            self.assertEqual(0,code);implicit.assert_not_called()
            self.assertEqual({},factory.call_args.args[0].proxies)
            self.assertEqual('https://another-trusted-host.invalid:8443/model/chat/completions',opener.open.call_args.args[0].full_url)
            result=json.loads((root/'out/ATTEMPT1-RESULT.json').read_bytes())
            self.assertEqual('direct',result['network_routing']['proxy_mode'])
            self.assertEqual('another-trusted-host.invalid',result['network_routing']['target_host'])
        self.assertEqual(before,config)

    def test_shared_profiles_explicitly_select_matching_direct_host(self):
        for name in ['executor.json','source-high-concurrency.json']:
            config=json.loads((ROOT/'config'/name).read_bytes())
            with self.subTest(profile=name),mock.patch.object(CALL.urllib.request,'build_opener') as factory:
                _,meta=CALL.network_transport(config)
            self.assertEqual('direct',config['network']['proxy_mode'])
            self.assertEqual(CALL.urllib.parse.urlsplit(config['base_url']).hostname,config['network']['direct_host'])
            self.assertEqual('direct',meta['proxy_mode']);self.assertEqual({},factory.call_args.args[0].proxies)

    def test_implicit_direct_rejects_credentials_query_or_fragment(self):
        config=self.config();config.pop('network',None)
        with mock.patch.object(CALL.urllib.request,'build_opener') as factory:
            for url in ['http://user:secret@target.invalid/v1','http://target.invalid/v1?query=1','http://target.invalid/v1#fragment','file:///tmp/endpoint']:
                config['base_url']=url
                with self.subTest(url=url),self.assertRaises(ValueError):CALL.network_transport(config)
        factory.assert_not_called()

if __name__=='__main__':unittest.main()

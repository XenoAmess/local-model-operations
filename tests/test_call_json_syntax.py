"""New automatic syntax metadata only; mocked SSE, socket creation forbidden."""
from contextlib import redirect_stdout, redirect_stderr
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
MODULE=Path(os.environ.get('CALL_SYNTAX_MODULE',ROOT/'scripts/call.py'))
spec=importlib.util.spec_from_file_location('syntax_candidate', MODULE)
CALL=importlib.util.module_from_spec(spec);spec.loader.exec_module(CALL)
CONFIG=Path(os.environ.get('CALL_SYNTAX_CONFIG',ROOT/'config/executor.json'))

class Response(io.BytesIO):
    status=200
    headers={}

def stream(text,finish='stop',done=True):
    event={'choices':[{'delta':{'content':text},'finish_reason':finish}]}
    return b'data: '+json.dumps(event,ensure_ascii=False).encode('utf-8')+b'\n\n'+(b'data: [DONE]\n\n' if done else b'')

class JsonSyntaxTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.config=copy.deepcopy(json.loads(CONFIG.read_bytes()))
        self.config["network"]={"proxy_mode":"environment"}  # Mocked urlopen fixture.
        self.config['base_url']='http://offline.invalid/v1'
        self.config['transient_retries'].update(maximum_attempts=1,backoff_seconds=[],jitter_ratio=0)
        self.request=self.root/'spec.json'
        self.request.write_bytes(json.dumps({'max_tokens':128,'messages':[{'role':'system','content':'synthetic'},{'role':'user','content':'synthetic source'},{'role':'user','content':'synthetic task'}]}).encode())
        self.network=mock.patch('socket.socket',side_effect=AssertionError('network forbidden')).start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ,{'LOCAL_MODEL_API_KEY':''}).start()
    def run_case(self,name,text,finish='stop',done=True):
        out=self.root/name
        with mock.patch.object(CALL.urllib.request,'urlopen',return_value=Response(stream(text,finish,done))) as transport,redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            code=CALL.dispatch(self.request,name,out,self.config,'synthetic','synthetic',None)
        self.assertEqual(0,self.network.call_count);self.assertEqual(1,transport.call_count)
        result=json.loads((out/'ATTEMPT1-RESULT.json').read_bytes())
        events=[json.loads(v) for v in (out/'EVENTS.jsonl').read_bytes().splitlines()]
        self.assertEqual(result['json_syntax'],[v for v in events if v['event']=='ATTEMPT_END'][0]['json_syntax'])
        self.assertEqual('NOT_YET_REVIEWED',result['candidate_review']);self.assertFalse(result['adopted'])
        summary=json.loads((out/'SUMMARY.json').read_bytes())
        self.assertEqual(result['json_syntax'],summary['attempts'][0]['json_syntax'])
        return code,result
    def test_long_valid_semantically_false_and_scalar_classes(self):
        text=json.dumps({'BigInteger_is_final':True,'complete':False,'long':'琉焰'*40000},ensure_ascii=False)
        code,r=self.run_case('long',text)
        self.assertEqual(0,code);self.assertEqual('VALID',r['json_syntax']['status']);self.assertEqual('object',r['json_syntax']['top_level_type'])
        self.assertEqual('OWNER_REVIEW_REQUIRED',r['json_syntax']['semantic_review'])
        for i,(text,kind) in enumerate([('[]','array'),('"琉焰\\n"','string'),('7','number'),('true','boolean'),('null','null')]):
            _,r=self.run_case('type'+str(i),text);self.assertEqual(('VALID',kind),(r['json_syntax']['status'],r['json_syntax']['top_level_type']))
    def test_invalid_unicode_crlf_location_is_numeric_and_private(self):
        code,r=self.run_case('invalid','{\r\n"琉焰": 1,\r\n"bad": }')
        self.assertEqual(1,code);m=r['json_syntax'];self.assertEqual('INVALID',m['status'])
        self.assertEqual({'class':'JSONDecodeError','line':3,'column':8,'offset':20},m['error'])
        self.assertEqual('Unicode code points',m['offset_units'])
        self.assertNotIn('琉焰',json.dumps(m,ensure_ascii=False));self.assertNotIn('Expecting',json.dumps(m))
    def test_length_and_incomplete_never_salvage_syntax(self):
        for name,text,finish,done,reason in [('lengthvalid','{}','length',True,'NON_STOP_FINISH'),('lengthfragment','{"bad":','length',True,'NON_STOP_FINISH'),('partialvalid','{}','stop',False,'INCOMPLETE_STREAM')]:
            code,r=self.run_case(name,text,finish,done)
            self.assertEqual(1,code);m=r['json_syntax'];self.assertEqual('UNKNOWN',m['status']);self.assertEqual(reason,m['reason'])
    def test_nonfinite_invalid_metadata_preserves_legacy_outcome(self):
        for i,text in enumerate(['NaN','Infinity','-Infinity','{"x":NaN}']):
            code,r=self.run_case('nonfinite'+str(i),text)
            self.assertEqual(0,code);self.assertTrue(r['candidate_complete']);self.assertIsNone(r['failure'])
            self.assertEqual('INVALID',r['json_syntax']['status']);self.assertEqual({'class':'NonJsonConstant'},r['json_syntax']['error'])
    def test_exact_utf8_limit_and_one_over_are_bounded_unknown(self):
        cap=CALL.JSON_SYNTAX_MAX_BYTES
        for i,text in enumerate(['"'+'x'*(cap-2)+'"','"'+'x'*(cap-1)+'"','"'+'焰'*(cap//3)+'"']):
            code,r=self.run_case('limit'+str(i),text)
            self.assertEqual(0,code);m=r['json_syntax']
            self.assertEqual('VALID' if i==0 else 'UNKNOWN',m['status'])
            if i:self.assertEqual('BYTE_LIMIT',m['reason'])
    def test_parser_resource_limit_and_unknown_do_not_escape(self):
        with mock.patch.object(CALL.json,'loads',side_effect=RecursionError):
            m=CALL.candidate_json_syntax('{}',complete_stream=True,finish='stop')
        self.assertEqual('UNKNOWN',m['status']);self.assertEqual('PARSER_LIMIT',m['reason'])
        m=CALL.candidate_json_syntax('\ud800',complete_stream=True,finish='stop')
        self.assertEqual('UNKNOWN',m['status']);self.assertEqual('UTF8_UNENCODABLE',m['reason'])

if __name__=='__main__':unittest.main()

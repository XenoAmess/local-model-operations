"""Caller registry boundary witnesses using only memory transport.

The registry storage is a public-API boundary fake here. The independent M7
suite owns real SQLite/cross-process persistence witnesses. No sockets are used.
"""
import builtins
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest import mock
import urllib.error


class RegistryFixtureError(ValueError):
    pass


class MemoryResponse:
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        yield b'data: {"choices":[{"delta":{"content":"{}"},"finish_reason":null}]}\n'
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
        yield b'data: [DONE]\n'


class RegistryModule(types.ModuleType):
    """Detect registry access even if caller attempts an eager import."""

    def __init__(self, store):
        super().__init__('request_registry')
        self.store = store
        self.class_accesses = 0
        self.RegistryError = RegistryFixtureError
        self.RegistryConflict = RegistryFixtureError
        self.RegistryFull = RegistryFixtureError

    def __getattr__(self, name):
        if name == 'RequestRegistry':
            self.class_accesses += 1
            return lambda *_args, **_kwargs: self.store
        raise AttributeError(name)


class RegistryBoundaryStore:
    def __init__(self, trace, *, fail_begin=False, fail_end=False):
        self.trace = trace
        self.fail_begin = fail_begin
        self.fail_end = fail_end
        self.begins = []
        self.ends = []

    def record_begin(self, events_path, event):
        self.trace.append(('registry_begin', event['attempt']))
        path = Path(events_path)
        if not path.is_absolute():
            raise AssertionError('caller supplied a relative EVENTS reference')
        last = json.loads(path.read_text(encoding='utf-8').splitlines()[-1])
        fields = ('event', 'at_utc', 'machine_id', 'task_id', 'owner', 'attempt')
        if any(last.get(key) != event.get(key) for key in fields) or event['event'] != 'POST_BEGIN':
            raise AssertionError('registration did not follow the exact EVENTS append')
        if self.fail_begin:
            raise RegistryFixtureError('injected BEGIN metadata failure')
        token = 'fixture-owned-token-' + str(event['attempt'])
        self.begins.append((token, str(path), dict(event)))
        return token

    def record_end(self, token, event):
        self.trace.append(('registry_end', event['attempt']))
        matches = [row for row in self.begins if row[0] == token]
        if len(matches) != 1:
            raise AssertionError('END used a token without this successful BEGIN')
        _token, events_path, begin = matches[0]
        if event['attempt'] != begin['attempt']:
            raise AssertionError('END token crossed attempts')
        last = json.loads(Path(events_path).read_text(encoding='utf-8').splitlines()[-1])
        fields = ('event', 'at_utc', 'machine_id', 'task_id', 'owner', 'attempt', 'post_invoked')
        if any(last.get(key) != event.get(key) for key in fields) or event['event'] != 'ATTEMPT_END':
            raise AssertionError('END registration preceded its exact EVENTS append')
        if self.fail_end:
            raise RegistryFixtureError('injected END metadata failure')
        self.ends.append((token, dict(event)))
        return True


class CallerRegistryBoundaries(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get('REQUEST_REGISTRY_TEST_ROOT', tempfile.gettempdir())).resolve()
        if not root.is_absolute() or not root.is_dir():
            raise AssertionError('explicit existing Native-owned scratch root required')
        self.temp = tempfile.TemporaryDirectory(prefix='caller-registry-', dir=root)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = Path(os.environ.get('REQUEST_REGISTRY_TEST_CALLER', Path(__file__).resolve().parents[1] / 'scripts/call_with_registry.py')).resolve()
        if not self.source.is_absolute() or not self.source.is_file():
            raise AssertionError('explicit selected caller source required')
        self.spec = self.base / 'spec.json'
        self.spec.write_text(json.dumps({'max_tokens': 1, 'messages': [
            {'role': 'system', 'content': 'fixture'},
            {'role': 'user', 'content': 'data-only fixture'},
            {'role': 'user', 'content': 'return an empty JSON object'}]}), encoding='utf-8')
        self.config = {
            'base_url': 'http://unused.invalid/v1', 'model': 'fixture',
            'prompting': {'system_template': 'fixture'}, 'defaults': {},
            'transient_retries': {'maximum_attempts': 2,
                                 'retry_http_statuses': [429, 503],
                                 'backoff_seconds': [0], 'jitter_ratio': 0},
            'timeouts': {'read_seconds': 1, 'total_seconds': 2}}

    @contextmanager
    def caller(self, store):
        registry_module = RegistryModule(store)
        spec = importlib.util.spec_from_file_location('selected_registry_boundary_caller', self.source)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict('sys.modules', {'request_registry': registry_module}):
            spec.loader.exec_module(module)
            proxy_time = types.SimpleNamespace(monotonic=time.monotonic, sleep=lambda _seconds: None)
            with mock.patch.object(module, 'time', proxy_time), \
                    mock.patch('builtins.print'):
                yield module, registry_module

    def dispatch(self, caller, leaf, *, enabled=True, stop=False):
        output = self.base / leaf
        stop_file = self.base / (leaf + '.stop')
        if stop:
            stop_file.write_bytes(b'fixture stop')
        if enabled:
            result = caller.dispatch(self.spec, 'registry-boundary-task', output,
                                     self.config, 'fixture-machine', 'fixture-owner', stop_file,
                                     request_registry_path=self.base / 'selected-registry.db')
        else:
            # Old public positional shape remains valid when the option is absent.
            result = caller.dispatch(self.spec, 'registry-boundary-task', output,
                                     self.config, 'fixture-machine', 'fixture-owner', stop_file)
        return result, output

    def bind_opener(self, caller, trace, *, fail_first=False):
        invoked = []

        def opener(request, *, timeout):
            invoked.append((request.data, timeout))
            trace.append(('http', len(invoked)))
            if fail_first and len(invoked) == 1:
                raise urllib.error.URLError('injected transient fixture transport failure')
            return MemoryResponse()

        patcher = mock.patch.object(caller, 'network_transport',
                                   return_value=(opener, {'fixture': 'no network'}))
        patcher.start()
        self.addCleanup(patcher.stop)
        return invoked

    def test_disabled_and_unissued_paths_never_register(self):
        trace = []
        store = RegistryBoundaryStore(trace)
        with self.caller(store) as (caller, registry_module):
            invoked = self.bind_opener(caller, trace)
            code, _out = self.dispatch(caller, 'disabled', enabled=False)
            self.assertEqual(0, code)
            self.assertEqual(0, registry_module.class_accesses)
            self.assertEqual([('http', 1)], trace)
            self.assertEqual(1, len(invoked))
            self.assertFalse((self.base / 'selected-registry.db').exists())

        trace = []
        store = RegistryBoundaryStore(trace)
        with self.caller(store) as (caller, _registry_module):
            invoked = self.bind_opener(caller, trace)

            def raw_open_failure(path, *_args, **_kwargs):
                if str(path).endswith('-RESPONSE.sse'):
                    raise OSError('injected local RAW open failure')
                return builtins.open(path, *_args, **_kwargs)

            with mock.patch.object(caller, 'open', raw_open_failure, create=True):
                code, out = self.dispatch(caller, 'raw-open-failure')
            self.assertEqual(1, code)
            self.assertEqual([], trace)
            self.assertEqual([], invoked)
            result = json.loads((out / 'ATTEMPT1-RESULT.json').read_text(encoding='utf-8'))
            self.assertIs(False, result['post_invoked'])
            self.assertIs(True, result['local_evidence_io_failure'])

        trace = []
        store = RegistryBoundaryStore(trace)
        with self.caller(store) as (caller, _registry_module):
            invoked = self.bind_opener(caller, trace)
            code, out = self.dispatch(caller, 'stopped-before-post', stop=True)
            self.assertEqual(1, code)
            self.assertEqual([], trace)
            self.assertEqual([], invoked)
            rows = [json.loads(line) for line in (out / 'EVENTS.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(['CANCELLED_BEFORE_POST'], [row['event'] for row in rows])

    def test_begin_failure_blocks_opener_and_transport_retry(self):
        trace = []
        store = RegistryBoundaryStore(trace, fail_begin=True)
        with self.caller(store) as (caller, _registry_module):
            invoked = self.bind_opener(caller, trace)
            code, out = self.dispatch(caller, 'begin-failure')
            self.assertEqual(1, code)
            self.assertEqual([('registry_begin', 1)], trace)
            self.assertEqual([], invoked)
            summary = json.loads((out / 'SUMMARY.json').read_text(encoding='utf-8'))
            self.assertEqual(1, len(summary['attempts']))
            result = summary['attempts'][0]
            self.assertIs(False, result['post_invoked'])
            self.assertIs(True, result['local_evidence_io_failure'])
            self.assertEqual([], store.ends)

    def test_end_failure_blocks_retry_and_successful_retry_pairs_tokens(self):
        trace = []
        store = RegistryBoundaryStore(trace, fail_end=True)
        with self.caller(store) as (caller, _registry_module):
            invoked = self.bind_opener(caller, trace, fail_first=True)
            with self.assertRaises(caller.LocalEvidenceIOError):
                self.dispatch(caller, 'end-failure')
            self.assertEqual([('registry_begin', 1), ('http', 1), ('registry_end', 1)], trace)
            self.assertEqual(1, len(invoked))
            self.assertEqual([], store.ends)

        trace = []
        store = RegistryBoundaryStore(trace)
        with self.caller(store) as (caller, _registry_module):
            invoked = self.bind_opener(caller, trace, fail_first=True)
            code, out = self.dispatch(caller, 'successful-retry')
            self.assertEqual(0, code)
            self.assertEqual([('registry_begin', 1), ('http', 1), ('registry_end', 1),
                              ('registry_begin', 2), ('http', 2), ('registry_end', 2)], trace)
            self.assertEqual(2, len(invoked))
            self.assertEqual(invoked[0][0], invoked[1][0], 'retry request bytes changed')
            self.assertEqual([1, 2], [row[2]['attempt'] for row in store.begins])
            self.assertEqual(2, len({row[0] for row in store.begins}))
            self.assertEqual(2, len(store.ends))
            self.assertTrue(all(row[1]['post_invoked'] is True for row in store.ends))
            self.assertEqual([1, 2], [row['attempt'] for row in json.loads((out / 'SUMMARY.json').read_text(encoding='utf-8'))['attempts']])


if __name__ == '__main__':
    unittest.main()

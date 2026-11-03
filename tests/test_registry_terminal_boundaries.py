"""Registry terminal history witness using only isolated SQLite DATA.

It covers two concrete original-model defects not exercised by the first eight
methods: a closed attempt being admitted again, and equal instants written with
different offsets. It uses only public APIs, an explicit source and own scratch.
"""
import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock


class RegistryTerminalBoundaries(unittest.TestCase):
    def test_closed_attempt_stays_unique_and_end_uses_instants(self):
        source = Path(os.environ.get('REQUEST_REGISTRY_TEST_MODULE', Path(__file__).resolve().parents[1] / 'scripts/request_registry.py')).resolve()
        scratch = Path(os.environ.get('REQUEST_REGISTRY_TEST_ROOT', tempfile.gettempdir())).resolve()
        self.assertTrue(source.is_absolute() and source.is_file())
        self.assertTrue(scratch.is_absolute() and scratch.is_dir())
        spec = importlib.util.spec_from_file_location('selected_terminal_registry', source)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('socket forbidden')), \
                mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')):
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory(prefix='registry-terminal-', dir=scratch) as temporary:
                root = Path(temporary)
                registry = module.RequestRegistry(root / 'registry.sqlite', max_records=4)
                events = root / 'EVENTS.jsonl'
                begin = {'event': 'POST_BEGIN', 'at_utc': '2026-11-03T09:00:00+08:00',
                         'machine_id': 'fixture-machine', 'task_id': 'fixture-task',
                         'owner': 'fixture-owner', 'attempt': 1}
                token = registry.record_begin(events, begin)
                end = {**begin, 'event': 'ATTEMPT_END',
                       'at_utc': '2026-11-03T02:00:00+01:00', 'post_invoked': True}
                # Both timestamps denote01:00UTC. Literal string order reverses it.
                self.assertIs(registry.record_end(token, end), True)
                equivalent = {**end, 'at_utc': '2026-11-03T01:00:00Z'}
                self.assertIs(registry.record_end(token, equivalent), False)
                with self.assertRaises(module.RegistryConflict):
                    registry.record_end(token, {**end, 'at_utc': '2026-11-03T01:00:01Z'})
                with self.assertRaises(module.RegistryConflict):
                    registry.record_begin(events, dict(begin))
                state = registry.snapshot()
                self.assertEqual((1, 1, 0, 1), (state['total_begun'], state['paired_ended'],
                                               state['unpaired'], state['invoked_ended']))
                self.assertEqual('CLOSED', state['records'][0]['state'])
                self.assertIs(state['records'][0]['post_invoked'], True)
                # There is free history: duplicate refusal cannot be capacity refusal.
                second = {**begin, 'attempt': 2, 'at_utc': '2026-11-03T01:00:02Z'}
                registry.record_begin(events, second)
                with self.assertRaises(module.RegistryConflict):
                    registry.record_end(token, {**end, 'attempt': 2})
                after = registry.snapshot()
                self.assertEqual((2, 1, 1), (after['total_begun'], after['paired_ended'], after['unpaired']))
                self.assertFalse(events.exists(), 'metadata API must not create/read an EVENTS file')


if __name__ == '__main__':
    unittest.main()

"""Opt-in synthetic intake DATA witnesses with explicit trusted dependency.

This file is outside default test_ discovery. Supply SOURCE_DIR, SCRATCH_DIR
and REGISTRAR_PATH environment bindings documented in docs/source-intake.md.
The registrar is executable trusted Python, not DATA. All its registration
subprocess calls are mocked here. Synthetic transfer fields are NOT_AUTHORIZATION.
Six public bindings require their own destination first; earlier private
five-method qualification does not execute this projection.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntakeRejectionObservabilityData(unittest.TestCase):
    def setUp(self):
        source = Path(os.environ['INTAKE_OBSERVABILITY_SOURCE_DIR']).resolve(strict=True)
        scratch = Path(os.environ['INTAKE_OBSERVABILITY_SCRATCH_DIR']).resolve(strict=True)
        if scratch.drive.upper() != 'D:' or not scratch.is_dir():
            raise ValueError('EXPLICIT_OWNED_D_SCRATCH_REQUIRED')
        self.temporary = tempfile.TemporaryDirectory(prefix='intake-observation-', dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'fixture-repo'
        self.repo.mkdir()
        (self.root / 'INTAKE').mkdir()
        self.registrar = Path(os.environ['INTAKE_OBSERVABILITY_REGISTRAR_PATH']).resolve(strict=True)
        if not self.registrar.is_file():
            raise ValueError('EXPLICIT_TRUSTED_REGISTRAR_FILE_REQUIRED')
        self.module = _load(source / 'source_intake.py', 'intake_rejection_data_candidate')
        self.spec = self.root / 'fixture-spec.json'
        self.spec.write_bytes(b'{}\n')

    def metadata(self, identity):
        return {'id': identity, 'task_id': identity, 'owner': '/fixture/source-owner',
                'spec_path': str(self.spec), 'output_path': str(self.root / ('output-' + identity)),
                'owner_zero_post_and_execute_transferred_to_models': True,
                'transfer_evidence': 'SYNTHETIC_DATA_NOT_AUTHORIZATION'}

    def ticket(self, identity, value=None, name=None):
        path = self.root / 'INTAKE' / (name or identity + '.ready.json')
        raw = json.dumps(self.metadata(identity) if value is None else value).encode('utf-8')
        path.write_bytes(raw)
        return path

    def once(self, maximum=256):
        return self.module.process_once(root=self.root, registrar_path=self.registrar,
                                        repo=self.repo, max_pending=maximum)

    def state(self):
        return json.loads((self.root / 'INTAKE-SCAN.STATE.json').read_bytes())

    def accepted(self):
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            'stage': 'READY_ATOMICALLY_APPENDED_NOT_POST_CREDIT', 'fixture_only': True}), stderr='')

    def observations(self):
        return sorted((self.root / 'INTAKE-REJECTIONS').glob('*.rejection.json'))

    def assert_no_final_receipt(self):
        self.assertEqual([], list((self.root / 'INTAKE-RECEIPTS').glob('*.receipt.json')))

    def test_early_schema_and_filename_rejections_are_safe_immutable_observations(self):
        wrong_id = self.metadata('badid')
        wrong_id['task_id'] = 'bad:task'
        self.ticket('badid', wrong_id)
        wrong_evidence = self.metadata('dict')
        wrong_evidence['transfer_evidence'] = {'not': 'a string'}
        self.ticket('dict', wrong_evidence)
        malformed = self.root / 'INTAKE' / 'partial.ready.json'
        malformed.write_bytes(b'{')
        self.ticket('unsafe', name='unsafe.name.ready.json')
        originals = {p.name: p.read_bytes() for p in (self.root / 'INTAKE').iterdir()}
        with mock.patch.object(self.module.subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            events = self.once()
            stored = {p.name: p.read_bytes() for p in self.observations()}
            self.assertEqual([], self.once())
        self.assertEqual(4, len(events))
        self.assertEqual(4, len(stored))
        self.assertEqual(stored, {p.name: p.read_bytes() for p in self.observations()})
        self.assertEqual(originals, {p.name: p.read_bytes() for p in (self.root / 'INTAKE').iterdir()})
        self.assert_no_final_receipt()
        reasons = set()
        for path in self.observations():
            self.assertRegex(path.name, r'^[0-9a-f]{64}\.rejection\.json$')
            self.assertEqual((self.root / 'INTAKE-REJECTIONS').resolve(), path.resolve().parent)
            item = json.loads(path.read_bytes())
            reasons.add(item['reason'])
            self.assertIs(item['registration_attempted'], False)
            self.assertIs(item['final_receipt'], False)
            self.assertIs(item['POST_credit'], False)
            self.assertNotIn('id', item)
            self.assertNotIn('raw', item)
            self.assertNotIn('input_path', item)
        self.assertEqual({'INVALID_ID', 'TRANSFER_EVIDENCE_REQUIRED',
                          'METADATA_INVALID_JSON_OR_SCHEMA', 'INVALID_INTAKE_FILENAME'}, reasons)
        state = self.state()
        self.assertEqual((4, 0, 4, 4, 0, 0), tuple(state[k] for k in (
            'seen_ready_tickets', 'tickets_with_final_receipt', 'tickets_without_final_receipt',
            'rejected_before_registration', 'registration_attempts', 'unclassified_pending')))
        self.assertIsNone(state['actual_registered_tasks'])
        self.assertIsNone(state['HTTP_inflight'])
        self.assertEqual('UNKNOWN', state['global_state'])

    def test_partial_can_complete_without_erasing_observation_or_closed_receipt(self):
        path = self.root / 'INTAKE' / 'later.ready.json'
        path.write_bytes(b'{')
        with mock.patch.object(self.module.subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            self.assertEqual(1, len(self.once()))
        old = {p.name: p.read_bytes() for p in self.observations()}
        self.assert_no_final_receipt()
        path.write_bytes(json.dumps(self.metadata('later')).encode('utf-8'))
        with mock.patch.object(self.module.subprocess, 'run', return_value=self.accepted()) as child:
            result = self.once()
        self.assertEqual(1, child.call_count)
        actual = child.call_args
        self.assertEqual([sys.executable, '-B', '-X', 'utf8', str(self.registrar.resolve()),
                          str(self.root / 'INTAKE-RECEIPTS' / 'later.ready.json.normalized.json'),
                          '--root', str(self.root), '--repo', str(self.repo)], actual.args[0])
        self.assertFalse(actual.kwargs['shell'])
        self.assertEqual(120, actual.kwargs['timeout'])
        self.assertEqual('READY_ATOMICALLY_APPENDED_NOT_POST_CREDIT', result[0]['stage'])
        receipt = self.root / 'INTAKE-RECEIPTS' / 'later.ready.json.receipt.json'
        receipt_raw = receipt.read_bytes()
        with mock.patch.object(self.module.subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            self.assertEqual([], self.once())
        self.assertEqual(receipt_raw, receipt.read_bytes())
        self.assertEqual(old, {p.name: p.read_bytes() for p in self.observations()})
        self.assertEqual(1, self.state()['tickets_with_final_receipt'])
        self.assertEqual(0, self.state()['tickets_without_final_receipt'])

    def test_rejection_does_not_consume_allowance_and_stop_is_explicit(self):
        (self.root / 'INTAKE' / 'a.ready.json').write_bytes(b'{')
        self.ticket('b')
        self.ticket('c')
        with mock.patch.object(self.module.subprocess, 'run', return_value=self.accepted()) as child:
            result = self.once(maximum=1)
        self.assertEqual(1, child.call_count)
        self.assertEqual(2, len(result))
        state = self.state()
        self.assertEqual(1, state['rejected_before_registration'])
        self.assertEqual(1, state['accepted_registration_results'])
        self.assertIs(state['processing_complete'], False)
        self.assertEqual(0, state['unclassified_pending'])
        self.assertEqual(2, state['valid_metadata_pending'])
        (self.root / 'INTAKE-STOP.json').write_bytes(b'{}\n')
        with mock.patch.object(self.module.subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            self.assertEqual([], self.once())
        state = self.state()
        self.assertIs(state['processing_complete'], False)
        self.assertEqual(2, state['unclassified_pending'])

    def test_capacity_pending_and_uncertain_reconciliation_remain_distinct(self):
        self.ticket('capacity')
        deferred = {'stage': 'QUEUE_CAPACITY_DEFERRED_BEFORE_READY_APPEND',
                    'this_attempt_appended_READY': False, 'reason': 'QUEUE_BYTE_LIMIT'}
        response = SimpleNamespace(returncode=3, stdout=json.dumps(deferred), stderr='')
        with mock.patch.object(self.module.subprocess, 'run', return_value=response) as child:
            result = self.once()
        self.assertEqual(1, child.call_count)
        self.assertEqual(deferred['stage'], result[0]['stage'])
        self.assert_no_final_receipt()
        normalized = self.root / 'INTAKE-RECEIPTS' / 'capacity.ready.json.normalized.json'
        old = normalized.read_bytes()
        self.assertEqual(1, self.state()['capacity_deferred'])
        self.assertIs(self.state()['processing_complete'], False)
        uncertain = SimpleNamespace(returncode=2, stdout='', stderr='fixture diagnostic')
        with mock.patch.object(self.module.subprocess, 'run', return_value=uncertain):
            second = self.once()
        self.assertEqual('INTAKE_RECONCILIATION_REQUIRED_NO_AUTO_RETRY', second[0]['stage'])
        self.assertEqual(old, normalized.read_bytes())
        self.assertEqual(1, self.state()['reconciliation_results'])
        self.assertEqual(0, self.state()['capacity_deferred'])
        with mock.patch.object(self.module.subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            self.assertEqual([], self.once())

    def test_empty_scan_bounds_and_observation_persistence_fail_closed(self):
        with mock.patch.object(self.module.subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            self.assertEqual([], self.once())
        self.assertEqual(0, self.state()['seen_ready_tickets'])
        self.assertIs(self.state()['processing_complete'], True)
        for name in ('a', 'b', 'c'):
            (self.root / 'INTAKE' / (name + '.ready.json')).write_bytes(b'{')
        with mock.patch.object(self.module, 'MAX_SCAN_FILES', 2):
            with self.assertRaisesRegex(ValueError, 'INTAKE_DIRECTORY_BOUND'):
                self.once()
        with mock.patch.object(self.module, 'MAX_REJECTIONS', 1):
            with self.assertRaisesRegex(ValueError, 'REJECTION_OBSERVATION_BOUND'):
                self.once()
        self.assertEqual(1, len(self.observations()))
        first = self.observations()[0].read_bytes()
        with mock.patch.object(self.module, '_observe_rejection', side_effect=OSError('fixture persistence failure')):
            with self.assertRaises(OSError):
                self.once()
        self.assertEqual(first, self.observations()[0].read_bytes())
        self.assert_no_final_receipt()


    def test_public_cli_requires_every_operator_path_before_import_or_loop(self):
        root, registrar, repo = str(self.root), str(self.registrar), str(self.repo)
        incomplete = [[], ['--root', root, '--registrar', registrar],
                      ['--root', root, '--repo', repo],
                      ['--registrar', registrar, '--repo', repo]]
        for arguments in incomplete:
            with self.subTest(arguments=arguments):
                with mock.patch.object(self.module, '_registrar', side_effect=AssertionError('NO_DEPENDENCY_IMPORT')), \
                     mock.patch.object(self.module, 'process_once', side_effect=AssertionError('NO_INTAKE_ENTRY')), \
                     mock.patch.object(self.module, 'run', side_effect=AssertionError('NO_LOOP_ENTRY')), \
                     contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as failure:
                        self.module.main(arguments)
                self.assertEqual(2, failure.exception.code)


if __name__ == '__main__':
    unittest.main()

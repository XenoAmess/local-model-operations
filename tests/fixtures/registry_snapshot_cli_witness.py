"""New frozen-copy CLI DATA witnesses. Native is the sole first executor."""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class FrozenRegistrySnapshotCliWitness(unittest.TestCase):
    def setUp(self):
        self.cli = Path(os.environ['REGISTRY_SNAPSHOT_CLI']).resolve()
        root = Path(os.environ['REGISTRY_SNAPSHOT_TEST_ROOT']).resolve()
        self.temporary = tempfile.TemporaryDirectory(prefix='frozen-registry-cli-', dir=root)
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def _database(self, name='registry # percent%.sqlite', *, rows=3, extra_meta=False, large=False):
        path = self.root / name
        with contextlib.closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE registry_meta (singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL, max_records INTEGER NOT NULL)')
            db.execute('CREATE TABLE registry_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL UNIQUE, events_path TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>0), machine_id TEXT NOT NULL, task_id TEXT NOT NULL, owner TEXT NOT NULL, begin_at_utc TEXT NOT NULL, end_at_utc TEXT, post_invoked INTEGER CHECK(post_invoked IN (0,1)), UNIQUE(events_path,attempt))')
            db.execute('INSERT INTO registry_meta VALUES (1,1,1000)')
            if extra_meta:
                db.execute('INSERT INTO registry_meta VALUES (2,1,1000)')
            for index in range(rows):
                end = None if index == 0 else '2026-11-03T02:00:00.000000+00:00'
                invoked = None if index == 0 else int(index % 2 == 1)
                events = str(self.root / (('e' * 3400 if large else 'events') + str(index) + '.jsonl'))
                db.execute('INSERT INTO registry_rows (token,events_path,attempt,machine_id,task_id,owner,begin_at_utc,end_at_utc,post_invoked) VALUES (?,?,?,?,?,?,?,?,?)',
                    ('private-begin-token-' + str(index), events, index + 1,
                     'machine', 'task', 'owner', '2026-11-03T01:00:00.000000+00:00', end, invoked))
        return path

    def _run(self, *arguments):
        return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(self.cli), *map(str, arguments)],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=10, shell=False)

    def _failed(self, process):
        self.assertEqual(2, process.returncode)
        self.assertEqual(b'', process.stdout)
        self.assertEqual(1, len(process.stderr.splitlines()))
        error = json.loads(process.stderr)
        self.assertEqual({'error'}, set(error))
        self.assertIsInstance(error['error'], str)
        self.assertNotIn(b'Traceback', process.stderr)

    def test_frozen_projection_counts_uri_and_no_write(self):
        path = self._database()
        before = path.read_bytes()
        names_before = sorted(item.name for item in self.root.iterdir())
        process = self._run(path, '--limit', '1')
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual(b'', process.stderr)
        self.assertEqual(1, len(process.stdout.splitlines()))
        report = json.loads(process.stdout)
        self.assertEqual((3, 2, 1, 1, 1), tuple(report[key] for key in
            ('total_begun', 'paired_ended', 'unpaired', 'invoked_ended', 'not_invoked_ended')))
        self.assertEqual(1, report['returned'])
        self.assertTrue(report['truncated'])
        self.assertEqual(1000, report['max_records'])
        self.assertEqual('OPEN_UNKNOWN', report['records'][0]['state'])
        self.assertIsNone(report['records'][0]['post_invoked'])
        self.assertEqual('THIS_REGISTRY_RECORDED_BOUNDARIES_ONLY', report['scope'])
        self.assertEqual('UNKNOWN', report['global_coverage'])
        self.assertEqual('UNKNOWN', report['live_http'])
        self.assertNotIn(b'private-begin-token', process.stdout)
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(names_before, sorted(item.name for item in self.root.iterdir()))

    def test_invalid_limits_companions_and_missing_input_are_quiet(self):
        path = self._database()
        for tail in [('--limit', '9' * 5000), ('--limit', '00'), ('--limit', '10001'),
                     ('--limit', '\u0661'), ('--other', '1')]:
            with self.subTest(tail_length=len(tail[1])):
                self._failed(self._run(path, *tail))
        missing = self.root / 'must-not-be-created.sqlite'
        self._failed(self._run(missing))
        self.assertFalse(missing.exists())
        before = path.read_bytes()
        for suffix in ('-wal', '-shm', '-journal'):
            companion = Path(str(path) + suffix)
            companion.write_bytes(b'owner-declared-pending-state')
            self._failed(self._run(path))
            self.assertEqual(b'owner-declared-pending-state', companion.read_bytes())
            companion.unlink()
        self.assertEqual(before, path.read_bytes())

    def test_utf8_bound_and_surrogate_path_reject_before_filesystem(self):
        spec = importlib.util.spec_from_file_location('new_frozen_snapshot_cli_under_test', self.cli)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for value in (str(self.root / ('\u754c' * 1400)), str(self.root / '\ud800')):
            with self.subTest(case='utf8' if '\ud800' not in value else 'surrogate'):
                with self.assertRaises(module.ReportError):
                    module._local_path(value)

    def test_extra_meta_and_oversized_report_are_rejected_without_partial_stdout(self):
        malformed = self._database('extra-meta.sqlite', extra_meta=True)
        before = hashlib.sha256(malformed.read_bytes()).hexdigest()
        self._failed(self._run(malformed))
        self.assertEqual(before, hashlib.sha256(malformed.read_bytes()).hexdigest())
        oversized = self._database('bounded-output.sqlite', rows=25, large=True)
        before = oversized.read_bytes()
        self._failed(self._run(oversized))
        self.assertEqual(before, oversized.read_bytes())


if __name__ == '__main__':
    unittest.main()

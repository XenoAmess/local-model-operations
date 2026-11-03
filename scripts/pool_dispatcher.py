#!/usr/bin/env python3
"""Portable explicit-ready queue dispatcher with durable at-most-one launch intent.

Integrates the authoritative read-only inputs (imported, never edited):

- pool_leases.LeaseStore / LeaseStoreFull: bounded client-admission leases.
  Lease counts are client reservations, never actual HTTP or server slots.
- pool_admission.select_pending: pure fairness selection (Runtime first, then
  round-robin source owners honoring the Runtime reserve). Not a lock.
- pool_observer.observe_stream: bounded read of caller EVENTS.jsonl evidence.

This module adds a separate persistent per-id dispatch claim in its own
SQLite database so processes sharing the same dispatch and lease databases
can never launch the same id, task_id or normalized output twice.

Hard boundaries honored here:

- One canonical call.py CLI per logical task owns all configured internal
  HTTP retries; the dispatcher never retries a child CLI itself.
- The stop file is shared with the caller and only halts new launches and
  the caller's next POST/internal retry. It never kills an active POST or
  child; no arbitrary process is ever discovered, signaled or swept.
- The dispatcher never creates caller-owned DISPATCH.claim, REQUEST, EVENTS
  or SUMMARY evidence; the caller owns those and rejects reused directories.
- Crash before or after OS launch remains conservative UNKNOWN on restart;
  no automatic resubmission, no PID scanning; claims/tombstones preserved.
- Lease HISTORY_FULL and dispatcher HISTORY_FULL are reported distinctly
  from CAPACITY; records are never removed to create room.
- Completion requires real observe_stream evidence: KNOWN status, exact
  expected stream identity, unended_attempts == 0, terminal PAIRED_END or
  STOPPED_BEFORE_NEXT_POST, or authoritative CANCELLED_BEFORE_POST. A
  nonzero child exit (including exit 2 with POST_BEGIN but no END/SUMMARY,
  because HTTPError.read can itself fail) never proves no POST happened.
- No import-time DB creation, process launch, network or CLI execution.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from pool_admission import FIELDS, select_pending
from pool_leases import LeaseStore, LeaseStoreFull
from pool_observer import observe_stream


READY_KEYS = FIELDS
LANES = ('source', 'runtime')
TERMINAL_STATES = ('COMPLETED', 'CANCELLED')
MAX_ID_BYTES = 512
MAX_FIELD_LEN = 4096
MAX_QUEUE_RECORDS = 256
MAX_QUEUE_BYTES = 65536
MAX_EVENTS_BYTES = 1048576


def _now():
    return time.time()


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _identity(value, label):
    if type(value) is not str or not value or '\0' in value:
        raise ValueError(label)
    try:
        size = len(value.encode('utf-8'))
    except UnicodeEncodeError:
        raise ValueError(label) from None
    if size > MAX_ID_BYTES:
        raise ValueError(label)
    return value


def _canonical(record):
    """Validate one explicit-ready 8-key record; never execute queue strings."""
    if not isinstance(record, dict) or set(record) != READY_KEYS:
        raise ValueError('RECORD_REQUIRES_EXACT_8_KEYS')
    clean = {}
    for key in READY_KEYS:
        value = record[key]
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_FIELD_LEN:
            raise ValueError('INVALID_RECORD_FIELD')
        clean[key] = value
    if clean['lane'] not in LANES:
        raise ValueError('INVALID_RECORD_LANE')
    for key in ('id', 'owner', 'task_id', 'machine_id'):
        _identity(clean[key], key)
        if clean[key].startswith('-'):
            raise ValueError('CLI_IDENTITY_MUST_NOT_START_DASH')
    for key in ('spec_path', 'config_path', 'output_path'):
        if not os.path.isabs(clean[key]):
            raise ValueError('PATHS_REQUIRE_ABSOLUTE')
    return clean


def _norm_output(value):
    """Physical alias normalization used only as the persistence uniqueness key."""
    return os.path.normcase(os.path.realpath(value))


def _norm_file(value):
    return os.path.normcase(os.path.realpath(value))


class DispatcherError(ValueError):
    pass


class Dispatcher:
    """Explicit-ready queue dispatcher; owns only its own Popen handles."""

    def __init__(self, db_path, lease_db_path, *, python_executable,
                 caller_path, stop_file, capacity=60, reserve_runtime=1,
                 max_records=10000, ttl=3600):
        for name, value in (('capacity', capacity), ('reserve_runtime', reserve_runtime),
                            ('max_records', max_records)):
            if type(value) is not int or value < 0:
                raise DispatcherError(name + ' requires a nonnegative integer')
        if not 1 <= capacity <= 10000 or not 0 <= reserve_runtime <= capacity \
                or not 1 <= max_records <= 100000:
            raise DispatcherError('capacity/reserve_runtime/max_records out of range')
        if type(ttl) not in (int, float) or not math.isfinite(ttl) or ttl <= 0:
            raise DispatcherError('ttl requires a finite positive number')
        self.capacity = capacity
        self.reserve_runtime = reserve_runtime
        self.max_records = max_records
        self.ttl = float(ttl)
        self.db_path = Path(db_path)
        self.lease_db_path = Path(lease_db_path)
        for path in (self.db_path, self.lease_db_path):
            if not path.is_absolute() or not path.parent.is_dir():
                raise DispatcherError('dedicated absolute database paths with existing parents required')
        self.python_executable = str(python_executable)
        self.caller_path = str(caller_path)
        self.stop_file = str(stop_file)
        for label, path in (('python_executable', self.python_executable),
                            ('caller_path', self.caller_path)):
            if not os.path.isabs(path) or not os.path.isfile(path):
                raise DispatcherError(label + ' must be an existing absolute file')
        if not os.path.isabs(self.stop_file):
            raise DispatcherError('stop_file must be absolute')
        self._children = {}
        self._history_full = False
        self._lease_history_full = False
        self._last_owner = None
        self._leases = LeaseStore(self.lease_db_path, capacity=capacity,
                                  reserve_runtime=reserve_runtime,
                                  max_records=max_records)
        self._init_db()
        self._load_fairness()

    # ------------------------------------------------------------------ #
    # Persistent dispatch ledger (separate from the lease history)       #
    # ------------------------------------------------------------------ #

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(str(self.db_path), timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _init_db(self):
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS dispatch_meta '
                       '(singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                       'version INTEGER NOT NULL, capacity INTEGER NOT NULL, '
                       'reserve_runtime INTEGER NOT NULL, max_records INTEGER NOT NULL, '
                       'ttl REAL NOT NULL, caller_path TEXT NOT NULL, '
                       'python_executable TEXT NOT NULL, stop_file TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS dispatch_state '
                       '(singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                       'last_owner TEXT)')
            db.execute("CREATE TABLE IF NOT EXISTS dispatch_tasks ("
                       "id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                       "spec_path TEXT NOT NULL, task_id TEXT NOT NULL, "
                       "output_path TEXT NOT NULL, output_norm TEXT NOT NULL, "
                       "config_path TEXT NOT NULL, machine_id TEXT NOT NULL, "
                       "lane TEXT NOT NULL, state TEXT NOT NULL, "
                       "detail TEXT NOT NULL, created REAL NOT NULL, "
                       "updated REAL NOT NULL)")
            db.execute('CREATE INDEX IF NOT EXISTS dispatch_task_id '
                       'ON dispatch_tasks(task_id)')
            db.execute('CREATE INDEX IF NOT EXISTS dispatch_output_norm '
                       'ON dispatch_tasks(output_norm)')
            row = db.execute('SELECT version,capacity,reserve_runtime,max_records,ttl,'
                             'caller_path,python_executable,stop_file '
                             'FROM dispatch_meta WHERE singleton=1').fetchone()
            expected = (2, self.capacity, self.reserve_runtime, self.max_records,
                        self.ttl, _norm_file(self.caller_path),
                        _norm_file(self.python_executable), _norm_file(self.stop_file))
            if row is None:
                if db.execute('SELECT COUNT(*) FROM dispatch_tasks').fetchone()[0]:
                    raise DispatcherError('dispatch history without configuration')
                db.execute('INSERT INTO dispatch_meta VALUES (1,?,?,?,?,?,?,?,?)', expected)
                db.execute('INSERT INTO dispatch_state VALUES (1,NULL)')
            elif tuple(row) != expected:
                raise DispatcherError('persistent dispatch configuration conflict')

    def _load_fairness(self):
        with self._transaction() as db:
            row = db.execute('SELECT last_owner FROM dispatch_state WHERE singleton=1').fetchone()
        owner = row['last_owner'] if row is not None else None
        self._last_owner = owner if isinstance(owner, str) and owner else None

    def _save_fairness(self, owner):
        if owner is None:
            return
        # Persist the last successful source owner for fairness across ticks
        # and restarts; Runtime launches do not shift source fairness.
        with self._transaction() as db:
            db.execute('UPDATE dispatch_state SET last_owner=? WHERE singleton=1', (owner,))
        self._last_owner = owner

    def _task_row(self, db, task_id):
        return db.execute('SELECT * FROM dispatch_tasks WHERE id=?', (task_id,)).fetchone()

    def _state_detail(self, row):
        try:
            detail = json.loads(row['detail']) if row['detail'] else {}
        except ValueError:
            detail = {}
        return row['state'], detail

    def _set_state(self, db, record, state, extra=None, *, now=None):
        when = now if now is not None else _now()
        detail = dict(record)
        detail['output_norm'] = _norm_output(record['output_path'])
        if extra:
            detail.update(extra)
        payload = json.dumps(detail, sort_keys=True)
        row = self._task_row(db, record['id'])
        if row is None:
            db.execute('INSERT INTO dispatch_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (record['id'], record['owner'], record['spec_path'],
                        record['task_id'], record['output_path'],
                        detail['output_norm'], record['config_path'],
                        record['machine_id'], record['lane'], state, payload,
                        when, when))
        else:
            db.execute('UPDATE dispatch_tasks SET state=?, detail=?, updated=? WHERE id=?',
                       (state, payload, when, record['id']))

    def _count_tasks(self, db):
        return db.execute('SELECT COUNT(*) FROM dispatch_tasks').fetchone()[0]

    def _identity_clash(self, db, record):
        clash = db.execute('SELECT id FROM dispatch_tasks WHERE task_id=? OR output_norm=?',
                           (record['task_id'], _norm_output(record['output_path']))).fetchone()
        return clash is not None and clash['id'] != record['id']

    def _immutable_conflict(self, db, record):
        row = self._task_row(db, record['id'])
        if row is None:
            return None
        for key in ('owner', 'spec_path', 'task_id', 'output_path',
                    'config_path', 'machine_id', 'lane'):
            if row[key] != record[key]:
                return 'IMMUTABLE_METADATA'
        return None

    def _admit(self, db, record):
        """Insert a fresh PENDING record; never remove records to create room."""
        if self._identity_clash(db, record) or self._immutable_conflict(db, record):
            return 'CONFLICT'
        if self._task_row(db, record['id']) is not None:
            return 'EXISTING'
        if self._count_tasks(db) >= self.max_records:
            self._history_full = True
            return 'HISTORY_FULL'
        self._set_state(db, record, 'PENDING', now=_now())
        return 'ADMITTED'

    def _claim(self, db, record):
        """Durable at-most-one launch intent, committed before Popen."""
        if self._task_row(db, record['id']) is None and self._count_tasks(db) >= self.max_records:
            self._history_full = True
            return False
        self._set_state(db, record, 'CLAIMED', {'claimed_at': _now()}, now=_now())
        return True

    def _claim_state(self, db, record):
        row = self._task_row(db, record['id'])
        if row is None:
            return 'MISSING'
        state, _detail = self._state_detail(row)
        return state

    def _mark_unknown(self, record, reason):
        self._leases.mark_unknown(record['id'], record['owner'])
        try:
            with self._transaction() as db:
                row = self._task_row(db, record['id'])
                if row is None:
                    return
                state, _detail = self._state_detail(row)
                if state in TERMINAL_STATES or state == 'UNKNOWN':
                    return
                self._set_state(db, record, 'UNKNOWN', {'unknown_reason': reason}, now=_now())
        except Exception:
            pass

    def _release(self, record, state, extra):
        # Release only after KNOWN observer evidence with unended_attempts=0,
        # terminal PAIRED_END/STOPPED_BEFORE_NEXT_POST, exact expected stream
        # identity, and no inconsistent local evidence.
        self._leases.release(record['id'], record['owner'], verified_no_live_post=True)
        with self._transaction() as db:
            row = self._task_row(db, record['id'])
            if row is None:
                return
            state_now, _detail = self._state_detail(row)
            if state_now in TERMINAL_STATES:
                return
            self._set_state(db, record, state, extra, now=_now())

    def _cancel_prelaunch(self, record):
        """Proven local prelaunch cancellation: release the newly acquired
        lease and keep a permanent cancelled tombstone."""
        self._leases.release(record['id'], record['owner'], verified_no_live_post=True)
        with self._transaction() as db:
            row = self._task_row(db, record['id'])
            if row is None:
                return
            state, _detail = self._state_detail(row)
            if state in TERMINAL_STATES:
                return
            self._set_state(db, record, 'CANCELLED',
                            {'cancel_reason': 'STOP_FILE_BEFORE_POPEN',
                             'cancelled_at': _stamp()}, now=_now())

    def _persist_lease_full(self, record):
        with self._transaction() as db:
            row = self._task_row(db, record['id'])
            if row is None:
                return
            state, _detail = self._state_detail(row)
            if state in TERMINAL_STATES:
                return
            self._set_state(db, record, 'UNKNOWN',
                            {'unknown_reason': 'LEASE_HISTORY_FULL'}, now=_now())

    # ------------------------------------------------------------------ #
    # Public surface                                                     #
    # ------------------------------------------------------------------ #

    def records(self):
        """Durable per-task states for owner review.

        A new instance without an original Popen handle exposes nonterminal
        old work as UNKNOWN and never auto launches or releases it.
        """
        with self._transaction() as db:
            rows = db.execute('SELECT id,state,detail FROM dispatch_tasks '
                              'ORDER BY created,id').fetchall()
        out = []
        for row in rows:
            state, detail = self._state_detail(row)
            prior_lease = self._leases.get(row['id']) if state == 'PENDING' else None
            if (state in ('CLAIMED', 'LAUNCHED') or state == 'PENDING' and prior_lease is not None) and row['id'] not in self._children:
                state = 'UNKNOWN'
                detail = dict(detail)
                detail['restart_note'] = ('no original Popen handle in this process; '
                                          'conservative UNKNOWN; never auto launched or released')
            entry = {'id': row['id'], 'state': state}
            entry.update({key: detail[key] for key in sorted(READY_KEYS) if key in detail})
            for key in ('unknown_reason', 'cancel_reason', 'exit_code', 'restart_note'):
                if key in detail:
                    entry[key] = detail[key]
            out.append(entry)
        return out

    def lease_snapshot(self):
        """Public lease snapshot lane counts (ACTIVE+UNKNOWN reservations)."""
        return self._leases.snapshot(now=_now())

    def tick(self, ready):
        """Reconcile only local child handles, then admit fresh records.

        Returns explicit launched/completed/deferred/history-full/conflict/
        unknown data without private request bodies.
        """
        summary = {'launched': [], 'completed': [], 'deferred': [],
                   'conflict': [], 'unknown': [], 'cancelled_before_launch': [],
                   'stopped': False, 'history_full': False, 'lease_history_full': False,
                   'errors': []}
        self._reap(summary)
        try:
            records = self._validate_queue(ready)
        except ValueError as exc:
            summary['errors'].append(str(exc))
            return summary
        if self._stop_present():
            summary['stopped'] = True
            self._reap(summary)
            summary['history_full'] = self._history_full
            summary['lease_history_full'] = self._lease_history_full
            return summary
        pending = self._admit_records(records, summary)
        if pending:
            self._load_fairness()
            snap = self.lease_snapshot()
            # Existing pure fairness selection: Runtime first, then round-robin
            # source owners, keeping space for future Runtime reservations.
            selection = select_pending(
                pending,
                occupied_source=snap['occupied_source'],
                occupied_runtime=snap['occupied_runtime'],
                capacity=self.capacity,
                reserve_runtime=self.reserve_runtime,
                last_owner=self._last_owner)
            summary['deferred'].extend(record['id'] for record in selection['remaining'])
            for record in selection['selected']:
                if self._stop_present():
                    summary['deferred'].append(record['id'])
                    continue
                self._admit_and_launch(record, summary)
        self._reap(summary)
        summary['history_full'] = self._history_full
        summary['lease_history_full'] = self._lease_history_full
        return summary

    def run_once(self, ready):
        """Drain this explicit snapshot; stop only prevents new launches."""
        summary = None
        while True:
            following = self.tick(ready)
            if summary is None:
                summary = following
            else:
                for key in ('launched', 'completed', 'conflict', 'unknown', 'cancelled_before_launch', 'errors'):
                    for value in following[key]:
                        if value not in summary[key]:
                            summary[key].append(value)
                for key in ('deferred', 'stopped', 'history_full', 'lease_history_full'):
                    summary[key] = following[key]
            if not self._children and not following['launched']:
                break
            time.sleep(0.05)
        return summary

    def run_file(self, queue_path):
        """Refresh only the explicit ready queue; stop drains owned children."""
        summary = self.tick([])
        while True:
            if self._stop_present():
                summary = self.tick([])
                if not self._children:
                    return summary
            else:
                try:
                    ready = _read_queue(queue_path)
                except (ValueError, OSError) as exc:
                    summary = self.tick([])
                    summary['errors'].append(type(exc).__name__)
                else:
                    summary = self.tick(ready)
            time.sleep(0.05)

    # ------------------------------------------------------------------ #
    # Queue validation and admission                                   #
    # ------------------------------------------------------------------ #

    def _validate_queue(self, ready):
        if not isinstance(ready, list) or len(ready) > MAX_QUEUE_RECORDS:
            raise ValueError('INVALID_QUEUE_SIZE')
        try:
            raw = json.dumps(ready, sort_keys=True)
        except TypeError:
            raise ValueError('INVALID_QUEUE_RECORD') from None
        if len(raw.encode('utf-8')) > MAX_QUEUE_BYTES:
            raise ValueError('QUEUE_BYTE_LIMIT')
        canonical = [_canonical(record) for record in ready]
        ids, task_ids, outputs = set(), set(), set()
        for record in canonical:
            norm = _norm_output(record['output_path'])
            if record['id'] in ids or record['task_id'] in task_ids or norm in outputs:
                raise ValueError('DUPLICATE_TASK_OR_OUTPUT_IN_QUEUE')
            ids.add(record['id'])
            task_ids.add(record['task_id'])
            outputs.add(norm)
        for record in canonical:
            for key in ('spec_path', 'config_path'):
                if not os.path.isfile(record[key]):
                    raise ValueError('REQUIRES_EXISTING_' + key)
        return canonical

    def _admit_records(self, records, summary):
        pending = []
        with self._transaction() as db:
            for record in records:
                verdict = self._admit(db, record)
                if verdict == 'CONFLICT':
                    summary['conflict'].append({'id': record['id'],
                                                'reason': 'TASK_OR_OUTPUT_IDENTITY_CONFLICT'})
                elif verdict == 'HISTORY_FULL':
                    summary['unknown'].append({'id': record['id'],
                                               'reason': 'DISPATCH_HISTORY_FULL'})
                elif verdict == 'ADMITTED':
                    pending.append(record)
                elif verdict == 'EXISTING' and self._claim_state(db, record) == 'PENDING':
                    # Registration alone never authorized launch. A preexisting
                    # lease is uncertainty, including a crash before CLAIMED.
                    if self._leases.get(record['id']) is None:
                        pending.append(record)
                    else:
                        summary['unknown'].append({'id': record['id'], 'reason': 'PRIOR_LEASE_WITHOUT_NEW_AUTHORITY'})
        return pending

    def _admit_and_launch(self, record, summary):
        token = record['id']
        try:
            decision = self._leases.acquire(token, record['owner'], lane=record['lane'],
                                            now=_now(), ttl=self.ttl)
        except LeaseStoreFull:
            # Lease bounded history full: distinct from CAPACITY; no tombstone
            # was removed and the record keeps its durable PENDING row.
            self._lease_history_full = True
            summary['deferred'].append(token)
            return
        if decision.outcome == 'CAPACITY':
            # Lease CAPACITY defers; it is distinct from HISTORY_FULL.
            summary['deferred'].append(token)
            return
        if decision.outcome == 'CONFLICT':
            summary['conflict'].append({'id': token, 'reason': 'LEASE_CONFLICT'})
            return
        if decision.outcome in ('EXISTING', 'RECOVERY_REQUIRED', 'TERMINAL'):
            # Only newly_acquired True permits launch; idempotent or expired
            # lease states never relaunch and never auto release.
            summary['unknown'].append({'id': token, 'reason': 'LEASE_' + decision.outcome})
            return
        if not decision.newly_acquired:
            summary['unknown'].append({'id': token, 'reason': 'LEASE_NOT_NEWLY_ACQUIRED'})
            return
        with self._transaction() as db:
            # Durable at-most-one launch intent committed before Popen; a
            # second process sharing these DBs sees CLAIMED/LAUNCHED and
            # never launches the same id, task_id or output twice.
            state = self._claim_state(db, record)
            if state != 'PENDING':
                self._leases.release(token, record['owner'], verified_no_live_post=False)
                summary['conflict'].append({'id': token, 'reason': 'STATE_' + state})
                return
            if not self._claim(db, record):
                self._leases.release(token, record['owner'], verified_no_live_post=False)
                summary['unknown'].append({'id': token, 'reason': 'DISPATCH_HISTORY_FULL'})
                return
        # Recheck stop immediately before Popen after the durable intent.
        if self._stop_present():
            self._cancel_prelaunch(record)
            summary['cancelled_before_launch'].append(token)
            return
        self._launch(record, summary)

    # ------------------------------------------------------------------ #
    # Launch: one canonical caller CLI per logical task                #
    # ------------------------------------------------------------------ #

    def _launch(self, record, summary):
        token = record['id']
        argv = [self.python_executable, '-B', self.caller_path,
                record['spec_path'], record['task_id'],
                '--output', record['output_path'],
                '--config', record['config_path'],
                '--machine-id', record['machine_id'],
                '--owner', record['owner'],
                '--stop-file', self.stop_file]
        out_dir = Path(record['output_path'])
        # The caller owns DISPATCH.claim/REQUEST/EVENTS/SUMMARY evidence.
        # Reject an existing caller evidence/claim instead of overwriting it.
        if (out_dir / 'EVENTS.jsonl').exists() or (out_dir / 'DISPATCH.claim').exists():
            self._mark_unknown(record, 'CALLER_EVIDENCE_EXISTS')
            summary['unknown'].append({'id': token, 'reason': 'CALLER_EVIDENCE_EXISTS'})
            return
        stdout_handle = stderr_handle = subprocess.DEVNULL
        try:
            stdout_handle = open(os.fspath(out_dir.parent / (out_dir.name + '.dispatcher-stdout.log')), 'ab')
            stderr_handle = open(os.fspath(out_dir.parent / (out_dir.name + '.dispatcher-stderr.log')), 'ab')
        except OSError:
            if hasattr(stdout_handle, 'close'):
                stdout_handle.close()
            if hasattr(stderr_handle, 'close'):
                stderr_handle.close()
            stdout_handle = stderr_handle = subprocess.DEVNULL
        try:
            try:
                if self._stop_present():
                    self._cancel_prelaunch(record)
                    summary['cancelled_before_launch'].append(token)
                    return
                proc = subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL,
                                        stdout=stdout_handle, stderr=stderr_handle,
                                        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            except OSError:
                # Ambiguous: the OS may or may not have started the child.
                self._mark_unknown(record, 'POPEN_ERROR')
                summary['unknown'].append({'id': token, 'reason': 'POPEN_ERROR'})
                return
            finally:
                for handle in (stdout_handle, stderr_handle):
                    if handle is not subprocess.DEVNULL and hasattr(handle, 'close'):
                        try:
                            handle.close()
                        except OSError:
                            pass
        except Exception:
            self._mark_unknown(record, 'LEDGER_AFTER_LAUNCH')
            summary['unknown'].append({'id': token, 'reason': 'LEDGER_AFTER_LAUNCH'})
            return
        self._children[token] = (proc, record['owner'], record['lane'])
        try:
            with self._transaction() as db:
                self._set_state(db, record, 'LAUNCHED',
                                {'launched_at': _stamp()}, now=_now())
        except Exception:
            # Ledger ambiguous after OS launch: conservative UNKNOWN, keep child.
            self._mark_unknown(record, 'LEDGER_AFTER_LAUNCH')
            summary['unknown'].append({'id': token, 'reason': 'LEDGER_AFTER_LAUNCH'})
        else:
            summary['launched'].append(token)
            if record['lane'] == 'source':
                self._save_fairness(record['owner'])

    # ------------------------------------------------------------------ #
    # Reconciliation and evidence-gated completion                     #
    # ------------------------------------------------------------------ #

    def _reap(self, summary):
        for token in list(self._children):
            proc, _owner, _lane = self._children[token]
            if proc.poll() is None:
                continue
            record = self._record_for(token)
            del self._children[token]
            if record is None:
                continue
            self._finalize(record, proc.returncode, summary)

    def _record_for(self, token):
        with self._transaction() as db:
            row = self._task_row(db, token)
        if row is None:
            return None
        _state, detail = self._state_detail(row)
        record = {key: detail[key] for key in READY_KEYS if key in detail}
        if set(record) != READY_KEYS:
            return None
        return record

    def _finalize(self, record, exit_code, summary):
        token = record['id']
        events_path = Path(record['output_path']) / 'EVENTS.jsonl'
        # Completion must use real observe_stream plus expected identity;
        # exit0/1/2 alone is never enough (HTTPError.read can itself fail,
        # so exit2 may show POST_BEGIN with no END/SUMMARY).
        report = observe_stream(events_path, max_bytes=MAX_EVENTS_BYTES)
        expected_identity = (record['task_id'], record['machine_id'], record['owner'])
        observed_identity = self._stream_identity(events_path, report.get('source_sha256'))
        identity_ok = observed_identity == expected_identity
        known = report['evidence_status'] == 'KNOWN'
        last_state = report.get('last_state', 'UNKNOWN')
        paired = last_state == 'PAIRED_END' and report['unended_attempts'] == 0
        stopped = last_state == 'STOPPED_BEFORE_NEXT_POST' and report['unended_attempts'] == 0
        # Authoritative prePOST cancellation: the caller proved it stopped before
        # invoking any POST for this task (zero POST), so the lease may release.
        cancelled = stopped and report.get('observed_POSTs') == 0 and report.get('event_counts', {}).get('CANCELLED_BEFORE_POST', 0) > 0
        if known and identity_ok and (paired or stopped):
            if cancelled:
                # Authoritative prePOST cancellation proves zero POST for this
                # task: release the lease and keep a permanent cancelled record.
                self._release(record, 'CANCELLED',
                              {'exit_code': exit_code, 'evidence': 'CANCELLED_BEFORE_POST'})
                summary['completed'].append({'id': token, 'exit': exit_code,
                                             'evidence': 'CANCELLED_BEFORE_POST'})
            else:
                self._release(record, 'COMPLETED',
                              {'exit_code': exit_code,
                               'evidence': 'PAIRED_END' if paired else 'STOPPED_BEFORE_NEXT_POST'})
                summary['completed'].append({'id': token, 'exit': exit_code,
                                             'evidence': 'PAIRED_END' if paired
                                             else 'STOPPED_BEFORE_NEXT_POST'})
            return
        # Ambiguous partial evidence (unpaired POST, BACKOFF then process loss,
        # malformed/partial/missing/oversize EVENTS, identity mismatch, or a
        # nonzero exit that cannot prove no POST) retains the lease.
        self._mark_unknown(record, 'EVIDENCE_INSUFFICIENT')
        summary['unknown'].append({
            'id': token, 'exit': exit_code, 'reason': 'EVIDENCE_INSUFFICIENT',
            'evidence_status': report['evidence_status'],
            'last_state': last_state,
            'identity_match': identity_ok,
            'issue': ((report['issues'][0].get('code') if isinstance(report['issues'][0], dict) else report['issues'][0]) if report['issues'] else None)})

    def _stream_identity(self, events_path, expected_sha256):
        """Exact expected stream identity check over caller EVENTS rows.

        Only the three identity fields the observer itself validates are
        compared; no path, free-text error or content fields are copied.
        """
        try:
            with Path(events_path).open('rb') as source:
                raw = source.read(MAX_EVENTS_BYTES + 1)
        except OSError:
            return None
        if len(raw) > MAX_EVENTS_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
            return None
        identity = None
        for line in raw.splitlines():
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                return None
            if not isinstance(row, dict):
                return None
            current = tuple(row.get(key) for key in ('task_id', 'machine_id', 'owner'))
            if any(value is not None and not isinstance(value, str) for value in current):
                return None
            if identity is None:
                identity = current
            elif identity != current:
                return None
        return identity

    # ------------------------------------------------------------------ #
    # Stop helper                                                        #
    # ------------------------------------------------------------------ #

    def _stop_present(self):
        return os.path.exists(self.stop_file)


def _build(parser=None):
    """CLI factory; no import-time execution."""
    arg_parser = argparse.ArgumentParser(
        prog='pool_dispatcher',
        description='Portable explicit-ready queue dispatcher (offline, stdlib only).')
    arg_parser.add_argument('--queue', required=True,
                            help='explicit JSON list of ready 8-key records; <=64 KiB')
    arg_parser.add_argument('--db', required=True,
                            help='persistent dispatch claim database (absolute path)')
    arg_parser.add_argument('--lease-db', required=True,
                            help='dedicated lease database (absolute path)')
    arg_parser.add_argument('--python', required=True,
                            help='selected explicit Python executable (absolute file)')
    arg_parser.add_argument('--caller', required=True,
                            help='canonical caller file (absolute file)')
    arg_parser.add_argument('--stop-file', required=True,
                            help='stop file shared with the caller (absolute path)')
    arg_parser.add_argument('--once', action='store_true',
                            help='admit one fair batch, then reap own handles')
    arg_parser.add_argument('--capacity', type=int, default=60)
    arg_parser.add_argument('--reserve-runtime', type=int, default=1)
    arg_parser.add_argument('--max-records', type=int, default=10000)
    arg_parser.add_argument('--ttl', type=float, default=3600)
    return arg_parser


def _read_queue(path):
    with Path(path).open('rb') as source:
        raw = source.read(MAX_QUEUE_BYTES + 1)
    if len(raw) > MAX_QUEUE_BYTES:
        raise ValueError('QUEUE_BYTE_LIMIT')
    return json.loads(raw.decode('utf-8'))


def main(argv=None):
    args = _build().parse_args(argv)
    try:
        dispatcher = Dispatcher(args.db, args.lease_db,
                                python_executable=args.python,
                                caller_path=args.caller,
                                stop_file=args.stop_file,
                                capacity=args.capacity,
                                reserve_runtime=args.reserve_runtime,
                                max_records=args.max_records,
                                ttl=args.ttl)
    except (DispatcherError, ValueError) as exc:
        print('pool_dispatcher: ' + str(exc), file=sys.stderr)
        return 2
    if args.once:
        try:
            summary = dispatcher.run_once(_read_queue(args.queue))
        except (ValueError, OSError):
            return 2
    else:
        summary = dispatcher.run_file(args.queue)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

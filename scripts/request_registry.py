"""Atomic local metadata for explicitly registered canonical HTTP boundaries.

OPEN_UNKNOWN means BEGIN was recorded, not that a socket or process is alive.
This module does not read EVENTS, discover callers, send HTTP or manage retries.
"""
from collections.abc import Mapping
from contextlib import contextmanager
import datetime
import os
from pathlib import Path
import sqlite3
import uuid


class RegistryError(ValueError):
    pass


class RegistryConflict(RegistryError):
    pass


class RegistryFull(RegistryError):
    pass


def _text(value, label, maximum):
    if type(value) is not str or not value or '\0' in value:
        raise RegistryError('invalid ' + label)
    try:
        length = len(value.encode('utf-8'))
    except UnicodeError:
        raise RegistryError('invalid ' + label) from None
    if length > maximum:
        raise RegistryError(label + ' exceeds byte limit')
    return value


def _local_path(value, label):
    try:
        raw = os.fspath(value)
    except TypeError:
        raise RegistryError('invalid ' + label) from None
    _text(raw, label, 4096)
    if not os.path.isabs(raw) or raw.startswith(('\\\\', '//')):
        raise RegistryError(label + ' requires an absolute local path')
    try:
        result = os.path.normcase(os.path.realpath(raw))
    except (OSError, ValueError):
        raise RegistryError('cannot normalize ' + label) from None
    _text(result, label, 4096)
    if result.startswith(('\\\\', '//')):
        raise RegistryError(label + ' must not resolve to UNC')
    return result


def _time(value):
    _text(value, 'at_utc', 128)
    try:
        parsed = datetime.datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timezone required')
        return parsed.astimezone(datetime.timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, OverflowError):
        raise RegistryError('timezone-aware ISO at_utc required') from None


def _event(event, kind):
    if not isinstance(event, Mapping) or event.get('event') != kind:
        raise RegistryError('expected ' + kind + ' event')
    try:
        identity = tuple(_text(event[key], key, 512)
                         for key in ('machine_id', 'task_id', 'owner'))
        attempt = event['attempt']
        stamp = _time(event['at_utc'])
    except KeyError:
        raise RegistryError('missing event metadata') from None
    if type(attempt) is not int or not 1 <= attempt <= 9223372036854775807:
        raise RegistryError('attempt requires a positive signed64 integer')
    return identity, attempt, stamp


class RequestRegistry:
    """Dedicated SQLite history; only explicit construction touches the DB."""

    def __init__(self, db_path, *, max_records=100000):
        if type(max_records) is not int or not 1 <= max_records <= 1000000:
            raise RegistryError('max_records requires integer1..1000000')
        self.db_path = _local_path(db_path, 'db_path')
        if not Path(self.db_path).parent.is_dir():
            raise RegistryError('db_path parent must already exist')
        self.max_records = max_records
        self._init_db()

    @contextmanager
    def _transaction(self, *, write=True):
        db = None
        try:
            db = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except sqlite3.Error as exc:
            if db is not None:
                try:
                    db.rollback()
                except sqlite3.Error:
                    pass
            raise RegistryError('registry SQLite operation failed: ' + type(exc).__name__) from exc
        except BaseException:
            if db is not None:
                try:
                    db.rollback()
                except sqlite3.Error:
                    pass
            raise
        finally:
            if db is not None:
                db.close()

    def _init_db(self):
        with self._transaction() as db:
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if not tables:
                db.execute('CREATE TABLE registry_meta '
                           '(singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                           'version INTEGER NOT NULL, max_records INTEGER NOT NULL)')
                db.execute('CREATE TABLE registry_rows '
                           '(id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL UNIQUE, '
                           'events_path TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>0), '
                           'machine_id TEXT NOT NULL, task_id TEXT NOT NULL, owner TEXT NOT NULL, '
                           'begin_at_utc TEXT NOT NULL, end_at_utc TEXT, '
                           'post_invoked INTEGER CHECK(post_invoked IN (0,1)), '
                           'UNIQUE(events_path,attempt))')
                db.execute('INSERT INTO registry_meta VALUES (1,1,?)', (self.max_records,))
            elif tables != {'registry_meta', 'registry_rows'}:
                raise RegistryConflict('dedicated registry database required')
            row = db.execute('SELECT version,max_records FROM registry_meta WHERE singleton=1').fetchone()
            if row is None or tuple(row) != (1, self.max_records):
                raise RegistryConflict('persistent registry configuration/version conflict')

    def record_begin(self, events_path, event):
        identity, attempt, stamp = _event(event, 'POST_BEGIN')
        path = _local_path(events_path, 'events_path')
        token = uuid.uuid4().hex
        with self._transaction() as db:
            if db.execute('SELECT 1 FROM registry_rows WHERE events_path=? AND attempt=?',
                          (path, attempt)).fetchone() is not None:
                raise RegistryConflict('stream attempt already has a BEGIN')
            previous = db.execute('SELECT machine_id,task_id,owner FROM registry_rows '
                                  'WHERE events_path=? LIMIT 1', (path,)).fetchone()
            if previous is not None and tuple(previous) != identity:
                raise RegistryConflict('immutable stream identity conflict')
            count = db.execute('SELECT COUNT(*) FROM registry_rows').fetchone()[0]
            if count >= self.max_records:
                raise RegistryFull('registry history full')
            db.execute('INSERT INTO registry_rows '
                       '(token,events_path,attempt,machine_id,task_id,owner,begin_at_utc) '
                       'VALUES (?,?,?,?,?,?,?)', (token, path, attempt, *identity, stamp))
        return token

    def record_end(self, token, event):
        _text(token, 'token', 128)
        identity, attempt, stamp = _event(event, 'ATTEMPT_END')
        if type(event.get('post_invoked')) is not bool:
            raise RegistryError('post_invoked requires boolean')
        invoked = int(event['post_invoked'])
        with self._transaction() as db:
            row = db.execute('SELECT * FROM registry_rows WHERE token=?', (token,)).fetchone()
            if row is None:
                raise RegistryConflict('unknown BEGIN token')
            if tuple(row[key] for key in ('machine_id', 'task_id', 'owner')) != identity or row['attempt'] != attempt:
                raise RegistryConflict('END identity does not match BEGIN token')
            if stamp < row['begin_at_utc']:
                raise RegistryConflict('END precedes BEGIN')
            if row['end_at_utc'] is not None:
                if row['end_at_utc'] == stamp and row['post_invoked'] == invoked:
                    return False
                raise RegistryConflict('terminal END is immutable')
            db.execute('UPDATE registry_rows SET end_at_utc=?,post_invoked=? WHERE token=?',
                       (stamp, invoked, token))
        return True

    def snapshot(self, *, limit=256):
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise RegistryError('limit requires integer1..10000')
        with self._transaction(write=False) as db:
            counts = db.execute('SELECT COUNT(*), '
                                'SUM(end_at_utc IS NOT NULL), '
                                'SUM(end_at_utc IS NOT NULL AND post_invoked=1), '
                                'SUM(end_at_utc IS NOT NULL AND post_invoked=0) '
                                'FROM registry_rows').fetchone()
            total, ended, invoked, not_invoked = (int(value or 0) for value in counts)
            rows = db.execute('SELECT events_path,attempt,machine_id,task_id,owner,begin_at_utc,'
                              'end_at_utc,post_invoked FROM registry_rows ORDER BY id LIMIT ?',
                              (limit,)).fetchall()
            records = []
            for row in rows:
                item = dict(row)
                item['post_invoked'] = None if row['post_invoked'] is None else bool(row['post_invoked'])
                item['state'] = 'OPEN_UNKNOWN' if row['end_at_utc'] is None else 'CLOSED'
                records.append(item)
            observed = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {'total_begun': total, 'paired_ended': ended, 'unpaired': total-ended,
                'invoked_ended': invoked, 'not_invoked_ended': not_invoked,
                'records': records, 'returned': len(records), 'truncated': total > len(records),
                'max_records': self.max_records, 'observed_at_utc': observed,
                'scope': 'THIS_REGISTRY_RECORDED_BOUNDARIES_ONLY',
                'global_coverage': 'UNKNOWN', 'live_http': 'UNKNOWN'}

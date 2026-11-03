"""Bounded snapshot report CLI for a frozen copy of a dedicated version-1 registry DB.

Input must be a trusted owner-provided closed, consolidated, immutable SQLite copy.
Stability and physical locality are owner configuration premises, not an OS sandbox
claim; a frozen copy with pending WAL/journal state is outside the contract.
This entry never creates directories, initializes/migrates schemas, imports or
constructs RequestRegistry, sets write pragmas, sends network requests, spawns
processes, reads EVENTS, expires history or retries failures. An unpaired BEGIN
record is not proof of a live HTTP request.

Usage: python snapshot_registry.py ABSOLUTE_LOCAL_DATABASE --limit 128
"""
import datetime
import json
import os
import sqlite3
import sys
from urllib.parse import quote

MAX_OUTPUT_BYTES = 65536


class ReportError(Exception):
    pass


def _local_path(value):
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise ReportError('database path is not valid UTF-8') from None
    if not value or '\0' in value or size > 4096:
        raise ReportError('database path must be a non-empty local path')
    if not os.path.isabs(value) or value.startswith(('\\\\', '//')):
        raise ReportError('database path must be an absolute local path')
    try:
        result = os.path.normcase(os.path.realpath(value))
    except (OSError, ValueError):
        raise ReportError('cannot normalize database path') from None
    try:
        size = len(result.encode('utf-8'))
    except UnicodeError:
        raise ReportError('normalized database path is not valid UTF-8') from None
    if size > 4096 or '\0' in result or result.startswith(('\\\\', '//')):
        raise ReportError('database path must not resolve to UNC or exceed bounds')
    if os.name == 'nt' and len(result) >= 2 and result[1] == ':':
        result = result[0].upper() + result[1:]
    return result


def _parse(argv):
    if len(argv) not in (1, 3):
        raise ReportError('usage: snapshot_registry.py ABSOLUTE_LOCAL_DATABASE [--limit N]')
    if len(argv) == 3:
        if argv[1] != '--limit' or argv[0].startswith('-') or argv[2].startswith('-'):
            raise ReportError('unknown option or misplaced limit')
        raw = argv[2]
        if not raw or len(raw) > 5 or any(ch not in '0123456789' for ch in raw) or str(int(raw)) != raw:
            raise ReportError('limit must be a canonical decimal integer')
        limit = int(raw)
        if not 1 <= limit <= 10000:
            raise ReportError('limit requires integer1..10000')
        return argv[0], limit
    return argv[0], 128


def _uri(path):
    escaped = path.replace('\\', '/')
    if os.name == 'nt' and len(escaped) >= 2 and escaped[1] == ':':
        escaped = '/' + escaped
    return 'file:' + quote(escaped, safe="/:@._-") + '?mode=ro&immutable=1'


def _snapshot(db, limit, max_records):
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
            'max_records': max_records, 'observed_at_utc': observed,
            'scope': 'THIS_REGISTRY_RECORDED_BOUNDARIES_ONLY',
            'global_coverage': 'UNKNOWN', 'live_http': 'UNKNOWN'}


def _validate(db):
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if tables != {'registry_meta', 'registry_rows'}:
        raise ReportError('dedicated registry database with exactly registry_meta/registry_rows required')
    meta = db.execute('SELECT singleton,version,max_records FROM registry_meta').fetchall()
    if len(meta) != 1:
        raise ReportError('singleton registry_meta version1 row required')
    singleton, version, max_records = meta[0]
    if (type(singleton) is not int or singleton != 1 or type(version) is not int
            or version != 1 or type(max_records) is not int or not 1 <= max_records <= 1000000):
        raise ReportError('unsupported registry version or max_records outside integer1..1000000')
    return max_records


def main(argv):
    db_arg, limit = _parse(list(argv))
    path = _local_path(db_arg)
    for companion in (path + '-wal', path + '-shm', path + '-journal'):
        if os.path.exists(companion):
            raise ReportError('frozen copy must have no pending -wal/-shm/-journal companion')
    if not os.path.isfile(path):
        raise ReportError('database file must exist and be a regular file')
    db = None
    try:
        db = sqlite3.connect(_uri(path), timeout=5, uri=True)
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        try:
            max_records = _validate(db)
            report = _snapshot(db, limit, max_records)
        finally:
            db.execute('COMMIT')
    except ReportError:
        raise
    except sqlite3.Error as exc:
        raise ReportError('registry SQLite read failed: ' + type(exc).__name__) from None
    finally:
        if db is not None:
            db.close()
    line = json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n'
    if len(line.encode('utf-8')) > MAX_OUTPUT_BYTES:
        raise ReportError('snapshot output exceeds 65536 byte bound')
    sys.stdout.write(line)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except ReportError as exc:
        sys.stderr.write(json.dumps({'error': str(exc)}, ensure_ascii=False,
                                    separators=(',', ':')) + '\n')
        sys.exit(2)

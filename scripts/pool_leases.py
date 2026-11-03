"""Bounded SQLite client-admission leases; never HTTP or process observations.

Use a dedicated local database. Transactions coordinate processes sharing that
database, not other machines or a service inference queue. Expiry is uncertainty:
it keeps consuming capacity until the owner explicitly attests no live POST.
Released tokens remain tombstones. Only a newly acquired decision permits the
integrator to proceed to its separate persistent dispatch claim.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import math
from pathlib import Path
import sqlite3


class LeaseStoreFull(RuntimeError):
    """The bounded history is full; no tombstones were silently removed."""


@dataclass(frozen=True)
class LeaseDecision:
    outcome: str
    newly_acquired: bool

    def __bool__(self):
        raise TypeError('Inspect newly_acquired explicitly; idempotence is not a new dispatch.')


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(label)
    return value


def _number(value, *, positive, label):
    if type(value) not in (int, float):
        raise ValueError(label)
    if value < 0 or (positive and value == 0) or value > 2 ** 53 or not math.isfinite(value):
        raise ValueError(label)
    return float(value)


def _identity(value, label):
    if type(value) is not str or not value or '\0' in value:
        raise ValueError(label)
    try:
        size = len(value.encode('utf-8'))
    except UnicodeEncodeError:
        raise ValueError(label) from None
    if size > 512:
        raise ValueError(label)
    return value


class LeaseStore:
    def __init__(self, db_path, *, capacity=60, reserve_runtime=1, max_records=10000):
        _integer(capacity, 1, 10000, 'capacity')
        _integer(reserve_runtime, 0, capacity, 'reserve_runtime')
        _integer(max_records, 1, 100000, 'max_records')
        self._limits = (capacity, reserve_runtime, max_records)
        self.db_path = Path(db_path)
        if not self.db_path.is_absolute() or not self.db_path.parent.is_dir():
            raise ValueError('dedicated absolute database path with existing parent required')
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS pool_meta '
                       '(singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                       'version INTEGER NOT NULL, capacity INTEGER NOT NULL, '
                       'reserve_runtime INTEGER NOT NULL, max_records INTEGER NOT NULL)')
            db.execute("CREATE TABLE IF NOT EXISTS pool_leases ("
                       "token TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                       "lane TEXT NOT NULL CHECK(lane IN ('source','runtime')), "
                       "created REAL NOT NULL, expires REAL NOT NULL, "
                       "state TEXT NOT NULL CHECK(state IN ('ACTIVE','UNKNOWN','RELEASED')))")
            row = db.execute('SELECT version,capacity,reserve_runtime,max_records '
                             'FROM pool_meta WHERE singleton=1').fetchone()
            expected = (1, capacity, reserve_runtime, max_records)
            if row is None:
                if db.execute('SELECT COUNT(*) FROM pool_leases').fetchone()[0]:
                    raise ValueError('lease history without configuration')
                db.execute('INSERT INTO pool_meta VALUES (1,?,?,?,?)', expected)
            elif tuple(row) != expected:
                raise ValueError('persistent lease configuration mismatch')

    @property
    def capacity(self):
        return self._limits[0]

    @property
    def reserve_runtime(self):
        return self._limits[1]

    @property
    def max_records(self):
        return self._limits[2]

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

    @staticmethod
    def _expire(db, now):
        db.execute("UPDATE pool_leases SET state='UNKNOWN' "
                   "WHERE state='ACTIVE' AND expires<=?", (now,))

    def acquire(self, token, owner, *, lane='source', now, ttl):
        token, owner = _identity(token, 'token'), _identity(owner, 'owner')
        if type(lane) is not str or lane not in ('source', 'runtime'):
            raise ValueError('lane')
        now = _number(now, positive=False, label='now')
        ttl = _number(ttl, positive=True, label='ttl')
        expires = now + ttl
        if not math.isfinite(expires) or expires > 2 ** 53 or expires <= now:
            raise ValueError('expiry')
        with self._transaction() as db:
            self._expire(db, now)
            row = db.execute('SELECT owner,lane,state FROM pool_leases WHERE token=?', (token,)).fetchone()
            if row is not None:
                if row['owner'] != owner or row['lane'] != lane:
                    return LeaseDecision('CONFLICT', False)
                return LeaseDecision({'ACTIVE': 'EXISTING', 'UNKNOWN': 'RECOVERY_REQUIRED',
                                      'RELEASED': 'TERMINAL'}[row['state']], False)
            total, sources = db.execute("SELECT COUNT(*),COALESCE(SUM(lane='source'),0) "
                                        "FROM pool_leases WHERE state IN ('ACTIVE','UNKNOWN')").fetchone()
            if total >= self.capacity or (lane == 'source' and sources >= self.capacity - self.reserve_runtime):
                return LeaseDecision('CAPACITY', False)
            if db.execute('SELECT COUNT(*) FROM pool_leases').fetchone()[0] >= self.max_records:
                raise LeaseStoreFull('bounded lease history requires explicit owner migration')
            db.execute("INSERT INTO pool_leases VALUES (?,?,?,?,?,'ACTIVE')", (token, owner, lane, now, expires))
            return LeaseDecision('ACQUIRED', True)

    def mark_unknown(self, token, owner):
        token, owner = _identity(token, 'token'), _identity(owner, 'owner')
        with self._transaction() as db:
            row = db.execute('SELECT owner,state FROM pool_leases WHERE token=?', (token,)).fetchone()
            if row is None or row['owner'] != owner or row['state'] == 'RELEASED':
                return False
            db.execute("UPDATE pool_leases SET state='UNKNOWN' WHERE token=?", (token,))
            return True

    def release(self, token, owner, *, verified_no_live_post):
        """Trust only the integrator's explicit True; this library cannot verify it."""
        token, owner = _identity(token, 'token'), _identity(owner, 'owner')
        if verified_no_live_post is not True:
            return False
        with self._transaction() as db:
            row = db.execute('SELECT owner FROM pool_leases WHERE token=?', (token,)).fetchone()
            if row is None or row['owner'] != owner:
                return False
            db.execute("UPDATE pool_leases SET state='RELEASED' WHERE token=?", (token,))
            return True

    def get(self, token):
        token = _identity(token, 'token')
        with self._transaction() as db:
            row = db.execute('SELECT token,owner,lane,created,expires,state FROM pool_leases WHERE token=?', (token,)).fetchone()
            return None if row is None else dict(row)

    def snapshot(self, *, now):
        now = _number(now, positive=False, label='now')
        with self._transaction() as db:
            self._expire(db, now)
            counts = {'ACTIVE': 0, 'UNKNOWN': 0, 'RELEASED': 0}
            for row in db.execute('SELECT state,COUNT(*) AS n FROM pool_leases GROUP BY state'):
                counts[row['state']] = row['n']
            occupied = counts['ACTIVE'] + counts['UNKNOWN']
            return {'capacity': self.capacity, 'reserve_runtime': self.reserve_runtime,
                    'max_records': self.max_records, 'records': sum(counts.values()),
                    'active': counts['ACTIVE'], 'unknown': counts['UNKNOWN'],
                    'released': counts['RELEASED'], 'occupied': occupied,
                    'scope': 'CLIENT_ADMISSION_ONLY_NOT_ACTUAL_HTTP_OR_SERVER_SLOT'}

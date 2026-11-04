"""Bounded caller-provided DATA projection; never an OS probe or authority.

No clock, file, process, network, DB, lock or lease access occurs here. A caller
must obtain and freeze its own independent observations. No returned status
authorizes clearing a lock, releasing a lease, restarting or replaying work.
"""
import datetime as dt
import hashlib
import json
import re

MAX_PACKET_BYTES = 65536
MAX_JSON_DEPTH = 8
MAX_TTL_SECONDS = 3600
_CORE = frozenset(("machine_id", "role", "owner_nonce", "pid", "birth_filetime"))
_IDENTITY = _CORE | {"argv"}
_PROCESS = frozenset(("pid", "birth_filetime", "argv"))
_LABEL = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_NONCE = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
_BIRTH = re.compile(r"[1-9][0-9]{0,19}\Z")
_STAMP = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?(?:Z|\+00:00)\Z")
_UTC = dt.timezone.utc
_EPOCH = dt.datetime(1970, 1, 1, tzinfo=_UTC)
_DATA_ERRORS = (ValueError, TypeError, OverflowError, UnicodeError, RecursionError)


def _reject(_value):
    raise ValueError("Invalid JSON value")


def _integer(text):
    if len(text.lstrip("-")) > 20:
        raise ValueError("Integer bound")
    return int(text)


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def _depth(text):
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("JSON depth bound")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("JSON nesting")
    if depth or quoted:
        raise ValueError("Incomplete JSON")


def _packet(raw, keys, schema):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_PACKET_BYTES:
        raise ValueError("Packet byte bound")
    text = raw.decode("utf-8")
    if text.startswith("\ufeff"):
        raise ValueError("BOM is not accepted")
    _depth(text)
    value = json.loads(text, object_pairs_hook=_object, parse_int=_integer,
                       parse_float=_reject, parse_constant=_reject)
    if type(value) is not dict or set(value) != keys or value["schema"] != schema:
        raise ValueError("Exact packet schema")
    return value


def _pid(value):
    if type(value) is not int or not 1 <= value <= 4294967295:
        raise ValueError("Native PID bound")
    return value


def _birth(value):
    if type(value) is not str or not _BIRTH.fullmatch(value) or int(value) > 18446744073709551615:
        raise ValueError("Canonical uint64 birth required")
    return value


def _argv(value):
    if type(value) is not list or not 1 <= len(value) <= 64:
        raise ValueError("Argv count bound")
    total = 0
    for index, token in enumerate(value):
        if type(token) is not str or "\0" in token or (index == 0 and not token):
            raise ValueError("Argv token")
        size = len(token.encode("utf-8"))
        if size > 4096:
            raise ValueError("Argv token byte bound")
        total += size
    if total > 32768:
        raise ValueError("Argv total byte bound")
    return tuple(value)


def _identity(value, *, core=False):
    if type(value) is not dict or set(value) != (_CORE if core else _IDENTITY):
        raise ValueError("Exact identity schema")
    for key, pattern in (("machine_id", _LABEL), ("role", _LABEL), ("owner_nonce", _NONCE)):
        if type(value[key]) is not str or not pattern.fullmatch(value[key]):
            raise ValueError("Identity label")
    result = (value["machine_id"], value["role"], value["owner_nonce"],
              _pid(value["pid"]), _birth(value["birth_filetime"]))
    return result if core else result + (_argv(value["argv"]),)


def _process(value):
    if type(value) is not dict or set(value) != _PROCESS:
        raise ValueError("Exact process schema")
    return _pid(value["pid"]), _birth(value["birth_filetime"]), _argv(value["argv"])


def _stamp(value):
    if type(value) is not str or len(value) > 35:
        raise ValueError("UTC timestamp required")
    match = _STAMP.fullmatch(value)
    if match is None:
        raise ValueError("UTC timestamp required")
    parts = tuple(int(match.group(index)) for index in range(1, 7))
    calendar = dt.datetime(*parts, tzinfo=_UTC)
    delta = calendar - _EPOCH
    fraction = (match.group(7) or "").ljust(9, "0")
    return (delta.days * 86400 + delta.seconds) * 1000000000 + int(fraction)


def _heartbeat(raw):
    row = _packet(raw, {"schema", "identity", "at_utc"},
                  "local-model-operations.pool-heartbeat/v1")
    return _identity(row["identity"]), _stamp(row["at_utc"])


def _observation(raw):
    row = _packet(raw, {"schema", "subject", "observed_at_utc", "state", "process", "exit_code"},
                  "local-model-operations.pool-process-observation/v1")
    subject = _identity(row["subject"], core=True)
    when = _stamp(row["observed_at_utc"])
    state = row["state"]
    if type(state) is not str or state not in ("ALIVE", "EXITED", "NOT_OBSERVED", "UNKNOWN"):
        raise ValueError("Observation state")
    process = None
    if state in ("ALIVE", "EXITED"):
        process = _process(row["process"])
        if state == "EXITED":
            if type(row["exit_code"]) is not int or not -2147483648 <= row["exit_code"] <= 4294967295:
                raise ValueError("Exit code bound")
        elif row["exit_code"] is not None:
            raise ValueError("Alive is not a terminal observation")
    elif row["process"] is not None or row["exit_code"] is not None:
        raise ValueError("No positive process was observed")
    return subject, when, state, process


def _age(now, when):
    return str(now - when) if when <= now else None


def project_liveness(expected_json: bytes, heartbeat_json: bytes | None,
                     observation_json: bytes | None, *, now_utc: str, ttl_seconds: int) -> dict:
    """Project only the supplied records, preserving the public refusal order."""
    result = {"schema": "local-model-operations.pool-liveness-projection/v1",
              "status": "UNKNOWN", "reason": "INVALID_EXPECTED",
              "basis": "CALLER_PROVIDED_JSON_ONLY_NOT_LIVE_PROBE_OR_AUTHORITY",
              "identity": None, "heartbeat_age_ns": None, "observation_age_ns": None,
              "ttl_seconds": None}

    def conclude(status, reason):
        result["status"], result["reason"] = status, reason
        return result

    try:
        now = _stamp(now_utc)
    except _DATA_ERRORS:
        return conclude("UNKNOWN", "INVALID_NOW")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        return conclude("UNKNOWN", "INVALID_TTL")
    result["ttl_seconds"] = ttl_seconds
    try:
        row = _packet(expected_json, {"schema", "identity"},
                      "local-model-operations.pool-liveness-expected/v1")
        expected = _identity(row["identity"])
    except _DATA_ERRORS:
        return conclude("UNKNOWN", "INVALID_EXPECTED")
    result["identity"] = dict(zip(("machine_id", "role", "owner_nonce", "pid", "birth_filetime"), expected[:5]))
    raw_argv = json.dumps(expected[5], ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    result["identity"]["argv_sha256"] = hashlib.sha256(raw_argv).hexdigest()
    heartbeat = observation = None
    if heartbeat_json is not None:
        try:
            heartbeat = _heartbeat(heartbeat_json)
        except _DATA_ERRORS:
            return conclude("UNKNOWN", "INVALID_HEARTBEAT")
        result["heartbeat_age_ns"] = _age(now, heartbeat[1])
    if observation_json is not None:
        try:
            observation = _observation(observation_json)
        except _DATA_ERRORS:
            return conclude("UNKNOWN", "INVALID_OBSERVATION")
        result["observation_age_ns"] = _age(now, observation[1])
    if heartbeat is not None and heartbeat[0] != expected:
        return conclude("UNKNOWN", "HEARTBEAT_IDENTITY_MISMATCH")
    if observation is not None:
        if observation[0] != expected[:5]:
            return conclude("UNKNOWN", "OBSERVATION_SUBJECT_MISMATCH")
        if observation[3] is not None and observation[3] != (expected[3], expected[4], expected[5]):
            return conclude("UNKNOWN", "PROCESS_IDENTITY_MISMATCH")
    if heartbeat is not None and heartbeat[1] > now:
        return conclude("UNKNOWN", "FUTURE_HEARTBEAT")
    if observation is not None and observation[1] > now:
        return conclude("UNKNOWN", "FUTURE_OBSERVATION")
    if observation is None:
        return conclude("NOT_OBSERVED", "OBSERVATION_MISSING")
    ttl_ns = ttl_seconds * 1000000000
    if now - observation[1] > ttl_ns:
        return conclude("STALE", "OBSERVATION_STALE")
    if observation[2] == "EXITED":
        return conclude("OBSERVED_EXIT", "EXIT_OBSERVED")
    if observation[2] == "NOT_OBSERVED":
        return conclude("NOT_OBSERVED", "PROCESS_NOT_OBSERVED")
    if observation[2] == "UNKNOWN":
        return conclude("UNKNOWN", "OBSERVATION_UNKNOWN")
    if heartbeat is None:
        return conclude("NOT_OBSERVED", "HEARTBEAT_MISSING")
    if now - heartbeat[1] > ttl_ns:
        return conclude("STALE", "HEARTBEAT_STALE")
    return conclude("VERIFIED_ACTIVE", "HEARTBEAT_AND_PROCESS_MATCH")

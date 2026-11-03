"""Bounded DATA validation. No I/O and no authority or liveness verification."""
import datetime as dt
import hashlib
import json
import re

MAX_INPUT_BYTES = 1048576
MAX_OUTPUT_BYTES = 2097152
MAX_ITEMS = 65
IDENTITY_KEYS = ("task_id", "owner", "body_sha256", "scope", "write_roots")
UTC = dt.timezone.utc


class PlanError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("Dispatch DATA rejected.")


def fail(code):
    raise PlanError(code)


def integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        fail("INVALID_INTEGER")
    return value


def text(value, maximum=32768):
    if type(value) is not str or not value.strip():
        fail("INVALID_STRING")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        fail("INVALID_UTF8")
    if size > maximum:
        fail("STRING_TOO_LONG")
    return value


def exact_keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        fail("INVALID_FIELDS")


def identifier(value):
    text(value, 128)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is None:
        fail("INVALID_ID")


def agent_id(value):
    text(value, 256)
    if re.fullmatch(r"/root(?:/[a-z0-9_]+)*", value) is None:
        fail("INVALID_AGENT_ID")


def d_path(value):
    text(value, 512)
    if re.fullmatch(r"D:/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+", value) is None:
        fail("INVALID_D_PATH")
    for part in value[3:].split("/"):
        stem = part.split(".", 1)[0].upper()
        if part in (".", "..") or part.endswith(".") or re.fullmatch(
            r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", stem
        ):
            fail("INVALID_D_PATH")
    return value


def sequence(value, maximum=MAX_ITEMS, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        fail("INVALID_COLLECTION")
    return value


def choices(value, allowed):
    sequence(value, 3, 1)
    if any(type(item) is not str or item not in allowed for item in value):
        fail("INVALID_ENUM")
    if len(set(value)) != len(value):
        fail("DUPLICATE_ENUM")


def utc(value):
    text(value, 32)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is None:
        fail("INVALID_UTC")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail("INVALID_UTC")


def fresh(value, now, max_age):
    age = (now - utc(value)).total_seconds()
    if age < 0 or age > max_age:
        fail("STALE_OR_FUTURE_INPUT")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json_integer(token):
    if len(token.lstrip("-")) > 9:
        fail("INTEGER_TOKEN_TOO_LONG")
    return int(token)


def _bad_number(_):
    fail("INVALID_JSON_NUMBER")


def decode(raw):
    if type(raw) is not bytes or len(raw) > MAX_INPUT_BYTES:
        fail("INVALID_INPUT_BYTES")
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_int=_json_integer, parse_float=_bad_number,
                              parse_constant=_bad_number)
    except PlanError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        fail("INVALID_JSON")
    nodes = 0
    stack = [(document, 0)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > 20000 or depth > 12:
            fail("JSON_TREE_TOO_LARGE")
        if type(value) is dict:
            if len(value) > 32:
                fail("OBJECT_TOO_LARGE")
            for key, child in value.items():
                try:
                    key_size = len(key.encode("utf-8"))
                except UnicodeError:
                    fail("INVALID_UTF8")
                if key_size > 64:
                    fail("KEY_TOO_LONG")
                stack.append((child, depth + 1))
        elif type(value) is list:
            sequence(value)
            stack.extend((child, depth + 1) for child in value)
        elif type(value) is str:
            try:
                if len(value.encode("utf-8")) > 32768:
                    fail("STRING_TOO_LONG")
            except UnicodeError:
                fail("INVALID_UTF8")
        elif value is not None and type(value) not in (bool, int):
            fail("INVALID_JSON_TYPE")
    if type(document) is not dict:
        fail("INVALID_DOCUMENT")
    return document


def identity(value):
    identifier(value["task_id"])
    agent_id(value["owner"])
    if type(value["body_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["body_sha256"]) is None:
        fail("INVALID_BODY_SHA")
    text(value["scope"], 2048)
    roots = sequence(value["write_roots"], 8, 1)
    for root in roots:
        d_path(root)
    if len({root.casefold() for root in roots}) != len(roots):
        fail("DUPLICATE_ROOT")


def same_identity(left, right):
    return all(left[key] == right[key] for key in IDENTITY_KEYS)


def unique_rows(rows, fields):
    for field in fields:
        values = [row[field] for row in rows]
        if len(set(values)) != len(values):
            fail("DUPLICATE_IDENTITY")


def validate(snapshot, pending, now, max_age, max_plans):
    exact_keys(snapshot, ("schema", "snapshot_id", "observed_at_utc", "complete", "agent_count", "agents"))
    if snapshot["schema"] != "xar.authorized-dispatch-snapshot/v1" or snapshot["complete"] is not True:
        fail("INCOMPLETE_SNAPSHOT")
    identifier(snapshot["snapshot_id"])
    agents = sequence(snapshot["agents"], 65, 1)
    if integer(snapshot["agent_count"], 1, 65) != len(agents):
        fail("INCOMPLETE_SNAPSHOT")
    fresh(snapshot["observed_at_utc"], now, max_age)
    for row in agents:
        exact_keys(row, ("agent_id", "status", "error", "same_task"))
        agent_id(row["agent_id"])
        if row["status"] not in ("RUNNING", "COMPLETED", "INTERRUPTED", "ERROR", "UNKNOWN"):
            fail("UNKNOWN_STATUS")
        if row["status"] != "ERROR":
            if row["error"] is not None or row["same_task"] is not None:
                fail("CONFLICTING_STATUS")
            continue
        error = row["error"]
        exact_keys(error, ("confirmed_kinds", "raw", "evidence"))
        choices(error["confirmed_kinds"], ("GUARD", "CAPACITY", "UNKNOWN"))
        text(error["raw"], 8192)
        text(error["evidence"], 2048)
        if row["same_task"] is not None:
            exact_keys(row["same_task"], IDENTITY_KEYS + ("operation",))
            identity(row["same_task"])
            if row["same_task"]["operation"] not in ("SEND", "FOLLOWUP"):
                fail("INVALID_OPERATION")
    unique_rows(agents, ("agent_id",))
    exact_keys(pending, ("schema", "bundle_id", "prepared_at_utc", "grants", "tasks"))
    if pending["schema"] != "xar.authorized-dispatch-pending/v1":
        fail("INVALID_PENDING_SCHEMA")
    identifier(pending["bundle_id"])
    fresh(pending["prepared_at_utc"], now, max_age)
    grants = sequence(pending["grants"])
    tasks = sequence(pending["tasks"], max_plans)
    for grant in grants:
        exact_keys(grant, IDENTITY_KEYS + ("grant_id", "state", "evidence", "not_before_utc", "expires_at_utc", "allowed_actions"))
        identity(grant)
        identifier(grant["grant_id"])
        if grant["state"] not in ("ACTIVE", "REVOKED"):
            fail("INVALID_GRANT_STATE")
        text(grant["evidence"], 2048)
        duration = (utc(grant["expires_at_utc"]) - utc(grant["not_before_utc"])).total_seconds()
        if not 0 < duration <= 86400:
            fail("INVALID_GRANT_WINDOW")
        choices(grant["allowed_actions"], ("SEND", "FOLLOWUP", "SAME_TASK_RETRY"))
    unique_rows(grants, ("grant_id", "task_id", "owner"))
    for task in tasks:
        exact_keys(task, IDENTITY_KEYS + ("grant_id", "body"))
        identity(task)
        identifier(task["grant_id"])
        body = text(task["body"], 16384)
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != task["body_sha256"]:
            fail("BODY_SHA_MISMATCH")
    unique_rows(tasks, ("task_id", "owner"))

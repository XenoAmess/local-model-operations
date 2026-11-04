"""Independent finite public DATA witnesses; Native binds the actual public projector.

Fixtures describe fictitious records, not an OS observation or process authority.
No target import, filesystem, process, network, database or lock operation occurs.
"""
import copy
import hashlib
import json
import unittest

_NOW = "2026-01-02T03:04:05.000000005Z"
_TTL = 5
_AT_HB = "2026-01-02T03:04:00.000000005Z"
_AT_OBS = "2026-01-02T03:04:05.000000004Z"
_AT_BEYOND_TTL = "2026-01-02T03:04:00.000000004Z"
_AT_OLD_HB = "2026-01-02T03:03:59.000000005Z"
_AT_FUTURE = "2026-01-02T03:04:05.000000006Z"
_BASIS = "CALLER_PROVIDED_JSON_ONLY_NOT_LIVE_PROBE_OR_AUTHORITY"
_KEYS = {"schema", "status", "reason", "basis", "identity",
         "heartbeat_age_ns", "observation_age_ns", "ttl_seconds"}
_UNSET = object()


def _identity():
    return {"machine_id": "witness-machine", "role": "source-dispatcher",
            "owner_nonce": "fixed_witness_nonce_01", "pid": 4242,
            "birth_filetime": "134000000000000019",
            "argv": ["python-fixture", "-B", "dispatcher_fixture.py", "--owner",
                     "source-dispatcher", "--nonce", "fixed_witness_nonce_01", ""]}


def _expected():
    return {"schema": "local-model-operations.pool-liveness-expected/v1",
            "identity": _identity()}


def _heartbeat(at=_AT_HB):
    return {"schema": "local-model-operations.pool-heartbeat/v1",
            "identity": _identity(), "at_utc": at}


def _observation(state="ALIVE", at=_AT_OBS):
    identity = _identity()
    subject = {key: identity[key] for key in
               ("machine_id", "role", "owner_nonce", "pid", "birth_filetime")}
    process = ({key: copy.deepcopy(identity[key]) for key in
                ("pid", "birth_filetime", "argv")}
               if state in ("ALIVE", "EXITED") else None)
    return {"schema": "local-model-operations.pool-process-observation/v1",
            "subject": subject, "observed_at_utc": at, "state": state,
            "process": process, "exit_code": 0 if state == "EXITED" else None}


def _bytes(packet):
    return (None if packet is None else
            json.dumps(packet, ensure_ascii=False, separators=(",", ":"),
                       allow_nan=False).encode("utf-8"))


def _summary():
    identity = _identity()
    argv = identity.pop("argv")
    identity["argv_sha256"] = hashlib.sha256(
        json.dumps(argv, ensure_ascii=False, separators=(",", ":"),
                   allow_nan=False).encode("utf-8")).hexdigest()
    return identity


def _changed(packet, path, value):
    packet = copy.deepcopy(packet)
    cursor = packet
    for field in path[:-1]:
        cursor = cursor[field]
    cursor[path[-1]] = copy.deepcopy(value)
    return packet


def make_suite(project_liveness):
    """Return three tests calling only the supplied actual public function."""
    class PublicLivenessWitness(unittest.TestCase):
        def _check(self, heartbeat, observation, status, reason, *, ttl=_TTL,
                   expected_identity=True, returned_ttl=_TTL,
                   heartbeat_age=_UNSET, observation_age=_UNSET):
            packets = (_bytes(_expected()), _bytes(heartbeat), _bytes(observation))
            original_packets = tuple(packets)
            result = project_liveness(
                expected_json=packets[0], heartbeat_json=packets[1],
                observation_json=packets[2], now_utc=_NOW, ttl_seconds=ttl)
            self.assertEqual(packets, original_packets)
            self.assertIs(type(result), dict)
            self.assertEqual(set(result), _KEYS)
            self.assertEqual(result["schema"],
                             "local-model-operations.pool-liveness-projection/v1")
            self.assertEqual((result["status"], result["reason"]), (status, reason))
            self.assertEqual(result["basis"], _BASIS)
            self.assertEqual(result["identity"], _summary() if expected_identity else None)
            self.assertEqual(result["ttl_seconds"], returned_ttl)
            for key, expected in (("heartbeat_age_ns", heartbeat_age),
                                  ("observation_age_ns", observation_age)):
                actual = result[key]
                if expected is not _UNSET:
                    self.assertEqual(actual, expected)
                elif actual is not None:
                    self.assertIs(type(actual), str)
                    self.assertRegex(actual, r"(?:0|[1-9][0-9]*)\Z")
            # Exact public keys and basis cannot carry cleanup/kill/DB authority.
            serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
            self.assertNotIn("dispatcher_fixture.py", serialized)
            return result

        def test_exact_owner_identity(self):
            self._check(_heartbeat(), _observation(), "VERIFIED_ACTIVE",
                        "HEARTBEAT_AND_PROCESS_MATCH",
                        heartbeat_age="5000000000", observation_age="1")
            reordered = _identity()["argv"]
            reordered[0], reordered[1] = reordered[1], reordered[0]
            differently_cased = _identity()["argv"]
            differently_cased[0] = "PYTHON-FIXTURE"
            cases = (
                ("PID reused; birth differs beyond float precision", "obs",
                 ("process", "birth_filetime"), "134000000000000020",
                 "PROCESS_IDENTITY_MISMATCH"),
                ("argv token order differs", "obs", ("process", "argv"),
                 reordered, "PROCESS_IDENTITY_MISMATCH"),
                ("heartbeat role differs", "hb", ("identity", "role"),
                 "other-source-role", "HEARTBEAT_IDENTITY_MISMATCH"),
                ("observation owner nonce differs", "obs", ("subject", "owner_nonce"),
                 "other_witness_nonce_02", "OBSERVATION_SUBJECT_MISMATCH"),
                ("argv case is exact", "hb", ("identity", "argv"),
                 differently_cased, "HEARTBEAT_IDENTITY_MISMATCH"),
                ("observation machine differs", "obs", ("subject", "machine_id"),
                 "other-witness-machine", "OBSERVATION_SUBJECT_MISMATCH"),
            )
            for name, target, path, value, reason in cases:
                with self.subTest(case=name):
                    heartbeat, observation = _heartbeat(), _observation()
                    if target == "hb":
                        heartbeat = _changed(heartbeat, path, value)
                    else:
                        observation = _changed(observation, path, value)
                    self._check(heartbeat, observation, "UNKNOWN", reason)

        def test_observation_is_not_metadata_or_absence(self):
            cases = (
                ("heartbeat alone", _heartbeat(), None,
                 "NOT_OBSERVED", "OBSERVATION_MISSING", _UNSET, _UNSET),
                ("explicit unknown", None, _observation("UNKNOWN"),
                 "UNKNOWN", "OBSERVATION_UNKNOWN", _UNSET, _UNSET),
                ("not observed is not exit", None, _observation("NOT_OBSERVED"),
                 "NOT_OBSERVED", "PROCESS_NOT_OBSERVED", _UNSET, _UNSET),
                ("observation stale by one ns", _heartbeat(),
                 _observation(at=_AT_BEYOND_TTL),
                 "STALE", "OBSERVATION_STALE", "5000000000", "5000000001"),
                ("fresh exit overrides old heartbeat", _heartbeat(_AT_OLD_HB),
                 _observation("EXITED"), "OBSERVED_EXIT", "EXIT_OBSERVED",
                 "6000000000", "1"),
                ("fresh exit needs no heartbeat", None, _observation("EXITED"),
                 "OBSERVED_EXIT", "EXIT_OBSERVED", None, "1"),
                ("old exit is not current exit proof", _heartbeat(_AT_OLD_HB),
                 _observation("EXITED", _AT_BEYOND_TTL),
                 "STALE", "OBSERVATION_STALE", _UNSET, _UNSET),
                ("live observation alone", None, _observation(),
                 "NOT_OBSERVED", "HEARTBEAT_MISSING", _UNSET, _UNSET),
                ("heartbeat stale by one ns", _heartbeat(_AT_BEYOND_TTL),
                 _observation(), "STALE", "HEARTBEAT_STALE", _UNSET, _UNSET),
                ("old LOCK_HELD is not a heartbeat",
                 {"state": "LOCK_HELD", "pid": 4242, "at_utc": _AT_HB}, None,
                 "UNKNOWN", "INVALID_HEARTBEAT", _UNSET, _UNSET),
            )
            for name, heartbeat, observation, status, reason, hb_age, obs_age in cases:
                with self.subTest(case=name):
                    self._check(heartbeat, observation, status, reason,
                                heartbeat_age=hb_age, observation_age=obs_age)

        def test_time_and_output_grant_no_control(self):
            cases = (
                ("future heartbeat by one ns", _heartbeat(_AT_FUTURE),
                 _observation(), "FUTURE_HEARTBEAT"),
                ("future observation by one ns", _heartbeat(),
                 _observation(at=_AT_FUTURE), "FUTURE_OBSERVATION"),
                ("exit cannot excuse future provided heartbeat",
                 _heartbeat(_AT_FUTURE), _observation("EXITED"), "FUTURE_HEARTBEAT"),
            )
            for name, heartbeat, observation, reason in cases:
                with self.subTest(case=name):
                    self._check(heartbeat, observation, "UNKNOWN", reason)
            for ttl in (0, True, 3601):
                with self.subTest(invalid_ttl=ttl, type_name=type(ttl).__name__):
                    self._check(_heartbeat(), _observation(), "UNKNOWN", "INVALID_TTL",
                                ttl=ttl, expected_identity=False, returned_ttl=None,
                                heartbeat_age=None, observation_age=None)
            first = self._check(_heartbeat(), _observation(), "VERIFIED_ACTIVE",
                                "HEARTBEAT_AND_PROCESS_MATCH",
                                heartbeat_age="5000000000", observation_age="1")
            first_identity = first["identity"]
            first["status"] = "CALLER_MUTATED_COPY"
            first_identity["role"] = "caller-mutated-copy"
            second = self._check(_heartbeat(), _observation(), "VERIFIED_ACTIVE",
                                 "HEARTBEAT_AND_PROCESS_MATCH",
                                 heartbeat_age="5000000000", observation_age="1")
            self.assertIsNot(first, second)
            self.assertIsNot(first_identity, second["identity"])

    return unittest.defaultTestLoader.loadTestsFromTestCase(PublicLivenessWitness)


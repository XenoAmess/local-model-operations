"""Independent synthetic oracle: no native launch or business source access."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

SPEC = importlib.util.spec_from_file_location(
    "trace_audit", Path(__file__).parents[1] / "scripts/audit_opencode_trace.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
FIXTURE = json.loads((Path(__file__).parent / "fixtures/opencode_trace_audit.json").read_text(encoding="utf-8"))


def write_trace(root, trace):
    for i, request in enumerate(trace["requests"]):
        directory = root / f"http-{i + 1:03d}"
        directory.mkdir()
        (directory / "REQUEST.json").write_text(json.dumps(request), encoding="utf-8")
        summary = trace["summaries"][i]
        if summary is not None:
            (directory / "SUMMARY.json").write_text(json.dumps(summary), encoding="utf-8")
    (root / "CLI-EVENTS.jsonl").write_text(
        "\n".join(json.dumps(event) for event in trace["events"]), encoding="utf-8")
    for key, name in (("CLI_ACTUAL", "CLI-ACTUAL.json"), ("OWNER_STOP", "OWNER-STOP.json")):
        if trace.get(key) is not None:
            (root / name).write_text(json.dumps(trace[key]), encoding="utf-8")


def pins(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class TraceAuditTests(unittest.TestCase):
    def audit_case(self, case):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_trace(root, case["trace"])
            before = pins(root)
            report = AUDIT.audit_trace(root)
            self.assertEqual(before, pins(root), "audit must not change input artifacts")
        serialized = json.dumps(report)
        for canary in FIXTURE["privacy_canaries"]:
            self.assertNotIn(canary, serialized)
        return report

    def test_independent_frozen_six_cases(self):
        for case in FIXTURE["cases"]:
            with self.subTest(case=case["id"]):
                report = self.audit_case(case)
                exp, tools, term = case["expected"], report["tools"], report["termination"]
                if case["id"] == "protocol-context-missing-summary":
                    self.assertEqual([{"record": 3, "error": "missing"}], report["errors"])
                else:
                    self.assertEqual([], report["errors"])
                if "tools" in exp:
                    self.assertEqual(exp["tools"], term["total_tool_invocations"])
                if "repeated_args_groups" in exp:
                    self.assertEqual(exp["repeated_args_groups"], len(tools["repetition_groups"]))
                if "raw_variants" in exp:
                    group = tools["repetition_groups"][0]
                    self.assertEqual(exp["raw_variants"], group["raw_output_sha_variants"])
                if "grep_normalized_variants" in exp:
                    self.assertEqual(exp["grep_normalized_variants"], group["grep_normalized_sha_variants"])
                if "same_args_calls" in exp:
                    self.assertEqual(exp["same_args_calls"], group["count"])
                    self.assertEqual(1, group["exact_same_result_subgroups"])
                if "tool_calls_HTTP" in exp:
                    self.assertEqual(exp["tool_calls_HTTP"], term["finish_counts"]["tool_calls"])
                    self.assertEqual(exp["owner_interrupted_HTTP"], term["owner_interrupted_attempts"])
                    self.assertEqual(exp["final_text"], term["final_text_present"])
                if "reads" in exp:
                    self.assertEqual(exp["reads"], len(tools["reads"]))
                if "explicit_byte_caps" in exp:
                    self.assertEqual(exp["explicit_byte_caps"], sum(r["byte_cap"] for r in tools["reads"]))
                if "range_continuation_flags" in exp:
                    self.assertEqual(exp["range_continuation_flags"], sum(r["range_continuation"] for r in tools["reads"]))
                if "continuation_offset" in exp:
                    read = tools["reads"][0]
                    self.assertEqual(exp["continuation_offset"], read["continuation_offset"])
                    self.assertEqual(exp["default_offset"], read["offset"])
                    self.assertEqual(exp["default_limit"], read["limit"])
                    self.assertEqual("UNKNOWN", read["source_parity"])
                if "second_unknown_result_ids" in exp:
                    second = report["requests"][1]
                    for expected, key in (("second_unknown_result_ids", "unknown_result"),
                                          ("second_duplicate_result_ids", "duplicate_result"),
                                          ("second_pending_call_ids", "pending_calls")):
                        self.assertEqual(exp[expected], second["linkage"][key])
                    self.assertFalse(second["system_unchanged"])
                    self.assertFalse(second["initial_user_unchanged"])
                    self.assertEqual(exp["unknown_summary_HTTP"], term["unknown_attempts"])

    def test_no_raw_parameters_errors_or_unknown_names_escape(self):
        trace = copy.deepcopy(FIXTURE["cases"][0]["trace"])
        secret = "SECRET_TOOL_OUTPUT C:/PRIVATE_CANARY_ROOT"
        request = trace["requests"][0]
        request.update(model=secret, tool_choice=secret, temperature=secret,
                       max_tokens=True, max_completion_tokens=secret,
                       response_format={"type": [secret]})
        request["messages"].append({"role": secret, "content": secret})
        event = trace["events"][0]
        event["part"]["tool"] = secret
        event["part"]["state"]["status"] = secret
        trace["summaries"][0].update(error=secret, finish_reason=secret,
                                      content_ttft_ms=float("nan"), ATTEMPT_END_utc=secret)
        report = self.audit_case({"trace": trace})
        self.assertIsNone(report["requests"][0]["max_tokens"])
        self.assertIsNone(report["requests"][0]["content_ttft_ms"])
        self.assertEqual("unknown", report["requests"][0]["tool_choice"])

    def test_context_content_parts_and_missing_baseline_stay_aligned(self):
        trace = copy.deepcopy(FIXTURE["cases"][0]["trace"])
        for request in trace["requests"]:
            for message in request["messages"]:
                if message["role"] in ("system", "user"):
                    message["content"] = [{"type": "text", "text": message["content"]}]
        report = self.audit_case({"trace": trace})
        self.assertTrue(report["requests"][1]["initial_user_unchanged"])
        trace["requests"][0]["messages"] = []
        report = self.audit_case({"trace": trace})
        self.assertIsNone(report["requests"][1]["system_unchanged"])

    def test_unrecognized_or_truncated_grep_never_claims_equivalence(self):
        trace = copy.deepcopy(FIXTURE["cases"][0]["trace"])
        trace["events"][1]["part"]["state"]["metadata"] = {"truncated": True}
        report = self.audit_case({"trace": trace})
        group = report["tools"]["repetition_groups"][0]
        self.assertIsNone(group["grep_normalized_sha_variants"])
        self.assertEqual(1, group["grep_normalization_unknown_results"])
        self.assertFalse(group["ordering_only_variation"])

    def test_nonnumeric_http_directory_and_malformed_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_trace(root, FIXTURE["cases"][0]["trace"])
            (root / "http-003").rename(root / "http-private-session-id")
            with (root / "CLI-EVENTS.jsonl").open("a", encoding="utf-8") as stream:
                stream.write('\n[]\n{"bad":\n')
            report = AUDIT.audit_trace(root)
            self.assertEqual(3, len(report["requests"]))
            self.assertEqual(2, len(report["errors"]))
            self.assertNotIn("private-session-id", json.dumps(report))

    def test_unknown_tool_identity_does_not_merge_and_nonjson_numbers_are_errors(self):
        trace = copy.deepcopy(FIXTURE["cases"][0]["trace"])
        trace["events"][0]["part"]["tool"] = "SECRET_TOOL_OUTPUT one"
        trace["events"][1]["part"]["tool"] = "SECRET_TOOL_OUTPUT two"
        self.assertEqual([], self.audit_case({"trace": trace})["tools"]["repetition_groups"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_trace(root, trace)
            with (root / "CLI-EVENTS.jsonl").open("a", encoding="utf-8") as stream:
                stream.write('\n{"part":{"input":NaN}}')
            self.assertEqual("invalid_json_object", AUDIT.audit_trace(root)["errors"][0]["error"])

    def test_stop_is_not_final_text_and_cli_reports_parse_failure(self):
        trace = copy.deepcopy(FIXTURE["cases"][0]["trace"])
        trace["summaries"][-1]["finish_reason"] = "stop"
        report = self.audit_case({"trace": trace})
        self.assertFalse(report["termination"]["final_text_present"])
        trace["events"].append({"type": "text", "part": {"text": "SECRET_TOOL_OUTPUT"}})
        termination = self.audit_case({"trace": trace})["termination"]
        self.assertTrue(termination["assistant_text_event_present"])
        self.assertIsNone(termination["final_text_present"])
        self.assertEqual("UNKNOWN_NO_RESPONSE_LINK", termination["final_text_association"])
        trace["summaries"][-1]["finish_reason"] = "tool_calls"
        self.assertIsNone(self.audit_case({"trace": trace})["termination"]["final_text_present"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_trace(root, trace)
            with redirect_stdout(io.StringIO()) as successful_output:
                self.assertEqual(0, AUDIT.main([str(root)]))
            self.assertEqual("local-model-operations.opencode-trace-audit/v1",
                             json.loads(successful_output.getvalue())["schema"])
            with redirect_stdout(io.StringIO()) as output:
                status = AUDIT.main([str(root / "PRIVATE_CANARY_ROOT")])
            self.assertEqual(1, status)
            self.assertNotIn("PRIVATE_CANARY_ROOT", output.getvalue())


if __name__ == "__main__":
    unittest.main()

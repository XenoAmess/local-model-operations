"""Finite independent admission oracles; no dispatcher, subprocess or network."""
import copy
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parent / "pool_admission.py"
if not MODULE.exists():
    MODULE = Path(__file__).parents[1] / "scripts/pool_admission.py"
SPEC = importlib.util.spec_from_file_location("admission_under_test", MODULE)
ADMISSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADMISSION)


def task(name, owner="a", lane="source"):
    return {"id": name, "owner": owner, "lane": lane, "spec_path": "spec.json",
            "task_id": name, "output_path": "evidence/" + name,
            "config_path": "profile.json", "machine_id": "offline-test"}


def ids(records):
    return [row["id"] for row in records]


class AdmissionTests(unittest.TestCase):
    def select(self, pending, **counts):
        before = copy.deepcopy(pending)
        result = ADMISSION.select_pending(pending, occupied_source=counts.pop("occupied_source", 0),
                                          occupied_runtime=counts.pop("occupied_runtime", 0), **counts)
        self.assertEqual(before, pending)
        return result

    def test_runtime_priority_does_not_double_spend_total_capacity(self):
        pending = [task("s1"), task("s2"), task("r1", lane="runtime"), task("r2", lane="runtime")]
        result = self.select(pending, capacity=3)
        self.assertEqual(["r1", "r2", "s1"], ids(result["selected"]))
        self.assertEqual(["s2"], ids(result["remaining"]))
        self.assertEqual(0, result["limits"]["free_after_selection"])

    def test_future_runtime_place_is_reserved_even_with_no_runtime_pending(self):
        pending = [task("s" + str(index)) for index in range(5)]
        first = self.select(pending, capacity=3)
        self.assertEqual(["s0", "s1"], ids(first["selected"]))
        later = self.select([task("r", lane="runtime")], capacity=3, occupied_source=2)
        self.assertEqual(["r"], ids(later["selected"]))

    def test_sources_round_robin_then_resume_after_last_owner(self):
        pending = [task("a1"), task("a2"), task("b1", "b"), task("b2", "b"), task("c1", "c")]
        result = self.select(pending, capacity=4, reserve_runtime=0)
        self.assertEqual(["a1", "b1", "c1", "a2"], ids(result["selected"]))
        resumed = self.select(pending, capacity=3, reserve_runtime=0, last_owner="b")
        self.assertEqual(["c1", "a1", "b1"], ids(resumed["selected"]))
        self.assertEqual(["a2", "b2"], ids(resumed["remaining"]))

    def test_existing_runtime_uses_reservation_without_reserving_it_twice(self):
        result = self.select([task("s")], capacity=3, occupied_source=1, occupied_runtime=1)
        self.assertEqual(["s"], ids(result["selected"]))
        self.assertEqual(0, result["limits"]["free_after_selection"])

    def test_overcapacity_reports_without_admission_cancellation_or_mutation(self):
        result = self.select([task("s"), task("r", lane="runtime")], occupied_source=60, occupied_runtime=2)
        self.assertEqual([], result["selected"])
        self.assertEqual(2, result["limits"]["existing_total_overcapacity"])
        self.assertEqual(1, result["limits"]["existing_source_reserved_limit_overage"])
        self.assertFalse(result["limits"]["already_POSTed_jobs_modified"])

    def test_finite_capacity_oracle_across_both_lanes(self):
        pending = [task("r" + str(index), lane="runtime") for index in range(3)]
        pending += [task("s" + str(index), str(index % 3)) for index in range(6)]
        for capacity in range(6):
            for source in range(8):
                for runtime in range(8):
                    with self.subTest(capacity=capacity, source=source, runtime=runtime):
                        reserve = min(1, capacity)
                        result = self.select(pending, capacity=capacity, reserve_runtime=reserve,
                                             occupied_source=source, occupied_runtime=runtime)
                        selected = result["selected"]
                        self.assertLessEqual(len(selected), max(0, capacity - source - runtime))
                        chosen_source = sum(row["lane"] == "source" for row in selected)
                        self.assertLessEqual(chosen_source, max(0, capacity - reserve - source))
                        self.assertEqual(len(pending), len(selected) + len(result["remaining"]))
                        self.assertEqual(len(selected), len(set(ids(selected))))

    def test_bad_counts_records_and_duplicate_logical_ids_are_rejected(self):
        for value in (True, -1, 1.5, float("inf"), "2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.select([task("a")], occupied_source=value)
        for pending in ([task("a"), task("a")], [task("a") | {"owner": " "}],
                        [task("a") | {"extra": 1}], [task("a") | {"lane": "unknown"}],
                        [task(str(index)) for index in range(257)]):
            with self.subTest(kind=len(pending)), self.assertRaises(ValueError):
                self.select(pending)
        with self.assertRaises(ValueError):
            self.select([], capacity=0, reserve_runtime=1)


if __name__ == "__main__":
    unittest.main()

"""Pure tests of fail-closed native and performance acceptance gates."""

import copy
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
RUNTIME = runpy.run_path(str(SCRIPTS / "runtime-tests.py"))
PERFORMANCE = runpy.run_path(str(SCRIPTS / "compare-performance.py"))


def report():
    distribution = {"samples": 60, "p50_ms": 2, "p95_ms": 4, "max_ms": 5}
    value = dict.fromkeys(PERFORMANCE["CONFIGURATION"], False)
    value.update(
        report_version=1,
        workload_version=2,
        posts=30,
        width=800,
        backend="invented-display",
        renderer="invented-renderer",
        runtime={"python": [3, 14, 9]},
        monitor_hz=60,
        profiled=False,
        failure=None,
        phases=[
            {
                "name": "feed-scroll",
                "row_binds": 30,
                "row_unbinds": 0,
                "image_calls": 3,
                "worker_jobs": 0,
                "post_rows": 30,
                "action_ms": distribution,
                "frame_work_ms": distribution,
                "worker_callback_ms": None,
                "scroll_distance": 1800,
                "cpu_ms": 10,
                "peak_rss_kib": 10000,
            }
        ],
    )
    return value


class TestGateTests(unittest.TestCase):
    def test_native_gate_rejects_empty_discovery_and_unexpected_skips(self):
        test = SimpleNamespace(id=lambda: "invented.NativeTests.test_render")
        errors = RUNTIME["result_errors"](SimpleNamespace(testsRun=0, skipped=[]))
        self.assertTrue(errors)
        skipped = SimpleNamespace(testsRun=1, skipped=[(test, "Display unavailable")])
        self.assertTrue(RUNTIME["result_errors"](skipped))
        self.assertFalse(RUNTIME["result_errors"](skipped, ["invented.NativeTests.test_render"]))
        self.assertTrue(RUNTIME["result_errors"](skipped, ["unrelated.*"]))
        self.assertFalse(RUNTIME["result_errors"](SimpleNamespace(testsRun=2, skipped=[])))

    def test_performance_identical_reports_pass_and_work_growth_fails(self):
        baseline = report()
        self.assertFalse(PERFORMANCE["compare_reports"](baseline, copy.deepcopy(baseline)))
        for metric in PERFORMANCE["WORK"]:
            changed = copy.deepcopy(baseline)
            changed["phases"][0][metric] += 1
            self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed), metric)

    def test_performance_rejects_a_throttled_or_under_sampled_scroll(self):
        baseline = report()
        changed = copy.deepcopy(baseline)
        changed["phases"][0]["frame_work_ms"]["samples"] = 4
        self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed))
        self.assertTrue(PERFORMANCE["compare_reports"](changed, changed))

    def test_performance_requires_matching_configuration_and_completed_workloads(self):
        baseline = report()
        for key in PERFORMANCE["CONFIGURATION"]:
            changed = copy.deepcopy(baseline)
            changed.pop(key)
            self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed), key)
        for key, value in (
            ("renderer", "other"),
            ("failure", "incomplete"),
            ("profiled", True),
            ("monitor_hz", 30),
            ("phases", []),
        ):
            changed = copy.deepcopy(baseline)
            changed[key] = value
            self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed), key)

    def test_performance_rejects_missing_metrics_and_relative_timing_regressions(self):
        baseline = report()
        for key in (
            *PERFORMANCE["WORK"],
            "action_ms",
            "frame_work_ms",
            "worker_callback_ms",
            "cpu_ms",
            "peak_rss_kib",
        ):
            changed = copy.deepcopy(baseline)
            changed["phases"][0].pop(key)
            self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed), key)
        changed = copy.deepcopy(baseline)
        changed["phases"][0]["frame_work_ms"]["p95_ms"] = 20
        self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed))
        changed = copy.deepcopy(baseline)
        changed["phases"][0]["frame_work_ms"] = None
        self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed))
        changed = copy.deepcopy(baseline)
        changed["phases"][0]["scroll_distance"] = 900
        self.assertTrue(PERFORMANCE["compare_reports"](baseline, changed))
        self.assertTrue(PERFORMANCE["compare_reports"](baseline, baseline, regression=float("nan")))

"""Compare matching native fixture reports; budgets are regressions, not a 60-fps claim."""

import argparse
import json
import math
from pathlib import Path

CONFIGURATION = (
    "report_version",
    "workload_version",
    "posts",
    "width",
    "backend",
    "renderer",
    "runtime",
    "reduced_motion",
    "idle_only",
    "control",
    "scroll_only",
    "startup_only",
    "interactions_only",
)
WORK = ("row_binds", "row_unbinds", "image_calls", "worker_jobs", "post_rows")
DISTRIBUTIONS = ("action_ms", "frame_work_ms", "worker_callback_ms")


def number(value):
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def compare_reports(baseline, candidate, *, regression=0.2, noise_ms=2.0, work_slack=0):
    errors = []
    if (
        not number(regression)
        or not number(noise_ms)
        or not isinstance(work_slack, int)
        or work_slack < 0
    ):
        return ["Comparison budgets must be finite and nonnegative."]
    for key in CONFIGURATION:
        if key not in baseline or key not in candidate or baseline[key] != candidate[key]:
            errors.append(f"Incompatible or missing configuration: {key}")  # noqa: PERF401 — conditional validation, not a transformation.
    for name, report in (("baseline", baseline), ("candidate", candidate)):
        if report.get("failure") is not None or "failure" not in report:
            errors.append(f"{name}: workload did not complete successfully")
        if report.get("profiled") is not False:
            errors.append(f"{name}: profiled timings cannot be compared")
    before_hz, after_hz = baseline.get("monitor_hz"), candidate.get("monitor_hz")
    if (
        not number(before_hz)
        or not number(after_hz)
        or before_hz <= 0
        or abs(before_hz - after_hz) > 0.5
    ):
        errors.append("Incompatible or missing monitor refresh rate")
    before, after = baseline.get("phases"), candidate.get("phases")
    if not isinstance(before, list) or not before or not isinstance(after, list):
        return [*errors, "Missing phase measurements"]
    if [p.get("name") for p in before] != [p.get("name") for p in after]:
        return [*errors, "Workload phase sequence differs"]
    if errors:
        return errors
    timing_samples = 0
    for index, (old, new) in enumerate(zip(before, after, strict=True)):
        name = f"{index}:{old['name']}"
        for key in WORK:
            a, b = old.get(key), new.get(key)
            if not number(a) or not number(b):
                errors.append(f"{name}: missing work metric {key}")
            elif b > a + work_slack:
                errors.append(f"{name}: {key} increased {a} -> {b} (slack {work_slack})")
        for key in DISTRIBUTIONS:
            if key not in old or key not in new:
                errors.append(f"{name}: missing {key}")
                continue
            a, b = old[key], new[key]
            if a is None and b is None:
                if key == "frame_work_ms" and "scroll" in old["name"]:
                    errors.append(f"{name}: scrolling has no frame-work samples")
                continue
            if a is None:
                # New work appearing where the baseline had no work needs review too.
                errors.append(f"{name}: {key} appeared without a comparable baseline")
                continue
            if not isinstance(a, dict) or not isinstance(b, dict):
                errors.append(f"{name}: missing distribution {key}")
                continue
            if (
                not number(a.get("samples"))
                or not number(b.get("samples"))
                or min(a["samples"], b["samples"]) < 1
            ):
                errors.append(f"{name}: empty distribution {key}")
                continue
            timing_samples += 1
            for percentile in ("p50_ms", "p95_ms", "max_ms"):
                x, y = a.get(percentile), b.get(percentile)
                if not number(x) or not number(y):
                    errors.append(f"{name}: missing {key}.{percentile}")
                elif y > x * (1 + regression) + noise_ms:
                    errors.append(f"{name}: {key}.{percentile} regressed {x} -> {y} ms")
        if "scroll" in old["name"]:
            for label, phase in (("baseline", old), ("candidate", new)):
                frame_work = phase.get("frame_work_ms")
                if (
                    not isinstance(frame_work, dict)
                    or not number(frame_work.get("samples"))
                    or frame_work["samples"] < 30
                ):
                    errors.append(
                        f"{name}: {label} has insufficient scroll frame samples (minimum 30)"
                    )
            a, b = old.get("scroll_distance"), new.get("scroll_distance")
            if not number(a) or not number(b) or min(a, b) <= 0:
                errors.append(f"{name}: missing actual scroll movement")
            elif abs(a - b) > max(1, a * 0.05):
                errors.append(f"{name}: scroll workloads differ ({a} -> {b} pixels)")
        for key, allowance in (("cpu_ms", 5.0), ("peak_rss_kib", 1024.0)):
            a, b = old.get(key), new.get(key)
            if not number(a) or not number(b):
                errors.append(f"{name}: missing {key}")
            elif b > a * (1 + regression) + allowance:
                errors.append(f"{name}: {key} regressed {a} -> {b}")
    if not timing_samples:
        errors.append("No comparable timing samples")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--max-regression", type=float, default=0.2, help="Relative budget, default 0.20"
    )
    parser.add_argument("--noise-ms", type=float, default=2.0)
    parser.add_argument("--work-slack", type=int, default=0)
    args = parser.parse_args()
    errors = compare_reports(
        json.loads(args.baseline.read_text(encoding="utf-8")),
        json.loads(args.candidate.read_text(encoding="utf-8")),
        regression=args.max_regression,
        noise_ms=args.noise_ms,
        work_slack=args.work_slack,
    )
    for error in errors:
        print("PERFORMANCE_CHECK_FAIL:", error)
    if errors:
        return 1
    print("PERFORMANCE_COMPARISON_PASS: matching workload; timing and work budgets met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

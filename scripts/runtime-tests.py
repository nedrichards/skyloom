"""Required GNOME runtime gate: missing display and unexpected skips are failures."""

import argparse
import fnmatch
import json
import sys
import unittest
from pathlib import Path


def result_errors(result, allowed_skips=()):
    errors = []
    if result.testsRun == 0:
        errors.append("No tests were discovered.")
    for test, reason in result.skipped:
        if not any(fnmatch.fnmatchcase(test.id(), pattern) for pattern in allowed_skips):
            errors.append(f"Unexpected skip: {test.id()}: {reason}")
    return errors


def require_runtime():
    import gi

    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Adw, Gdk, Gtk

    if sys.version_info < (3, 14):  # noqa: UP036 — this gate rejects an unsupported interpreter.
        raise RuntimeError("The native gate requires the supported Python 3.14 runtime.")
    if not Gtk.init_check() or Gdk.Display.get_default() is None:
        raise RuntimeError(
            "The native gate requires an available graphical display; skips are not acceptance."
        )
    Adw.init()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--allow-skip", action="append", default=[], metavar="TEST_ID_GLOB")
    parser.add_argument("--report", type=Path, help="Write an invented-data CI result summary")
    args = parser.parse_args()
    try:
        require_runtime()
    except (ImportError, ValueError, RuntimeError) as error:
        print(f"RUNTIME_PREFLIGHT_FAIL: {error}", file=sys.stderr)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({"preflight": str(error)}), encoding="utf-8")
        return 2
    suite = unittest.defaultTestLoader.discover(str(args.tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    errors = result_errors(result, args.allow_skip)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "tests": result.testsRun,
                    "failures": [test.id() for test, _ in result.failures],
                    "errors": [test.id() for test, _ in result.errors],
                    "skips": [(test.id(), reason) for test, reason in result.skipped],
                    "gate_errors": errors,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    for error in errors:
        print(error, file=sys.stderr)
    if errors or not result.wasSuccessful():
        return 1
    print(
        f"RUNTIME_TEST_PASS: {result.testsRun} tests, {len(result.skipped)} explicitly allowed skips"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

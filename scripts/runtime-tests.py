"""Required GNOME runtime gate: missing display and unexpected skips are failures."""

import argparse
import fnmatch
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

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Adw, Gtk

    if sys.version_info < (3, 14):  # noqa: UP036 — this gate rejects an unsupported interpreter.
        raise RuntimeError("The native gate requires the supported Python 3.14 runtime.")
    if not Gtk.init_check():
        raise RuntimeError(
            "The native gate requires an available graphical display; skips are not acceptance."
        )
    Adw.init()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--allow-skip", action="append", default=[], metavar="TEST_ID_GLOB")
    args = parser.parse_args()
    try:
        require_runtime()
    except (ImportError, ValueError, RuntimeError) as error:
        print(f"RUNTIME_PREFLIGHT_FAIL: {error}", file=sys.stderr)
        return 2
    suite = unittest.defaultTestLoader.discover(str(args.tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    errors = result_errors(result, args.allow_skip)
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

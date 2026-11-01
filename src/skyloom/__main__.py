import argparse
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")


def main():
    parser = argparse.ArgumentParser(description="Skyloom — a native client for Bluesky")
    parser.add_argument(
        "--demo", action="store_true", help="Use invented offline data; no account needed"
    )
    parser.add_argument(
        "--smoke-test", metavar="OUTPUT", help="Run demo interactions and save fixture screenshots"
    )
    parser.add_argument(
        "--smoke-scenario",
        default="full",
        choices=(
            "full",
            "navigation",
            "profile",
            "search",
            "labels",
            "conversation",
            "paging",
            "refresh",
            "offline",
            "preferences",
        ),
    )
    parser.add_argument(
        "--keyboard-test",
        action="store_true",
        help="Run isolated native X11 input checks with the local keyboard-event driver",
    )
    args = parser.parse_args()
    if args.smoke_scenario != "full" and not args.smoke_test:
        parser.error("--smoke-scenario requires --smoke-test and --demo")
    if args.smoke_test and not args.demo:
        parser.error("--smoke-test requires --demo; real accounts must never be captured")
    if args.keyboard_test and (not args.demo or args.smoke_test):
        parser.error("--keyboard-test requires --demo and a separate run from --smoke-test")
    if args.demo:
        os.environ["GSETTINGS_BACKEND"] = "memory"
    from gi.repository import Gtk

    if not Gtk.init_check():
        print("Skyloom needs a graphical Wayland or X11 session.", file=sys.stderr)
        return 1
    from .application import Application

    app = Application(
        demo=args.demo,
        smoke=args.smoke_test,
        keyboard_test=args.keyboard_test,
        smoke_scenario=args.smoke_scenario,
    )
    app.callback_failed = False
    if args.smoke_test or args.keyboard_test:
        import traceback

        def failed(kind, value, tb):
            app.callback_failed = True
            traceback.print_exception(kind, value, tb)
            if hasattr(app, "keyboard_runner"):
                app.keyboard_runner.stop()
            else:
                app.quit()

        sys.excepthook = failed
    result = app.run([sys.argv[0]])
    if app.callback_failed:
        return 1
    if hasattr(app, "smoke_runner") and app.smoke_runner.failure:
        return 1
    if hasattr(app, "keyboard_runner") and app.keyboard_runner.failure:
        return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())

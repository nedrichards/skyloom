# Testing

Run native tests, GUI smoke and profiling sequentially on a GNOME 51 desktop.
Keep test windows unobstructed: occlusion can suspend GTK frame callbacks.
Use invented records and temporary data; never capture account credentials,
databases or real feeds.

## Automated gates

```sh
./scripts/check.sh
./scripts/test-in-flatpak.sh --installed
./scripts/smoke-flatpak.sh
```

`check.sh` runs lint, formatting, compilation, shell syntax, desktop/schema
validation and checkout tests in the installed Flatpak runtime. `meson test` uses
the same runtime runner: a missing display or unexpected skip fails the gate. The second
command tests installed modules. Smoke runs the installed demo application and
writes ignored fixture screenshots to `screenshots/demo/`. Only the reviewed
images in `screenshots/showcase/` belong in Git.

For a focused smoke, use:

```sh
flatpak run --filesystem="$PWD/screenshots/demo" com.nedrichards.Skyloom --demo \
  --smoke-test "$PWD/screenshots/demo" --smoke-scenario conversation
```

See `src/skyloom/__main__.py` for command-line options and `smoke.py` for
scenario names. When invoking directly, expose the output directory with
Flatpak `--filesystem`. Repeat visual checks with `--env=ADW_DEBUG_HIGH_CONTRAST=1`
and `--env=SKYLOOM_SMOKE_FONT="Adwaita Sans 16"` on the Flatpak command.

Shared display setup lives in `tests/gtk_support.py`; reusable content and
startup fixtures live beside it. Test classes should use these helpers rather
than instantiate other test classes.

## Display troubleshooting

Wayland full-suite runs have timed out waiting for native frames. To diagnose
functional behaviour separately, run the source suite under X11/Cairo:

```sh
flatpak run --user --socket=x11 --nosocket=wayland \
  --env=GDK_BACKEND=x11 --env=GSK_RENDERER=cairo \
  --command=python3 --filesystem="$PWD:ro" --env=PYTHONPATH="$PWD/src" \
  com.nedrichards.Skyloom "$PWD/scripts/runtime-tests.py" --tests "$PWD/tests"
```

Use `--env=PYTHONPATH=/app/share/skyloom` for installed modules. Flatpak filters
host environment variables, so pass overrides explicitly. Cairo results do not
establish default-renderer performance.

The optional `--demo --keyboard-test` runner needs X11/Xwayland, a focused window
and `SKYLOOM_KEYBOARD_DRIVER` pointing to `scripts/keyboard-event.py`. Input
injection currently reports XTest success without delivering key events here. The
harness rejects missing input before checking selection; native controller tests do not
replace physical keyboard, pointer or touch checks.

## Packaging and acceptance

After a packaging change, build offline, export/install, run installed tests and
smoke, and inspect permissions with `flatpak info --user --show-permissions
com.nedrichards.Skyloom`. Validate AppStream separately from export.
`scripts/keyring-self-test.py` provides an optional isolated dummy-keyring check.

Report the layer tested. Mock HTTP tests use the real SDK but do not establish
live-service interoperability. Remaining human checks are in
[ROADMAP.md](ROADMAP.md); profiling instructions are in [PERFORMANCE.md](PERFORMANCE.md).

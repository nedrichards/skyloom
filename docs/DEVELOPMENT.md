# Development

The source repository is [nedrichards/skyloom](https://github.com/nedrichards/skyloom)
(private; access is required), with the initial import on `main`. Local Flatpak
builds and preview acceptance remain separate from source hosting; no hosted
release or public download is configured.

See [sharing and contributions](../CONTRIBUTING.md) for the project's maintenance
approach and [the source sharing review](REPOSITORY_REVIEW.md) for upload scope,
local-file exclusions and the remaining Git-history verification requirement.

## Environment

Python 3.14, GTK 4.24, libadwaita 1.10, libsecret, GdkPixbuf/Glycin, Meson and GNOME SDK/runtime 51. The tested Flatpak runtime uses Python 3.14.9. Runtime packages are supplied by GNOME; the SDK, Unicode segmenter and Python transitive dependencies are pinned in requirements.lock and python-dependencies.json.

On a normal development system, install the native GI libraries, Meson and Ninja through your usual environment, then:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-dev.lock
PATH="$PWD/.venv/bin:$PATH" meson setup build --prefix="$PWD/local-install"
meson compile -C build
meson test -C build --print-errorlogs
glib-compile-schemas data
GSETTINGS_SCHEMA_DIR="$PWD/data" PYTHONPATH="$PWD/src" .venv/bin/python -m skyloom --demo
./scripts/lint.sh
```

A development Python without GI can run the domain/SDK tests; the GI-dependent tests report skips. Use GNOME 51 and the installed Flatpak for the authoritative runtime checks. Some host Python 3.14.7 pytest runs intermittently stalled awaiting thread completion; the cause remains unresolved, and the GNOME 51 Python 3.14.9 tests are the reproducible gate used for delivery.

Meson must be configured with the intended Python first in PATH. Changing interpreters requires a fresh build directory.

## Flatpak

Install org.gnome.Platform//51, org.gnome.Sdk//51 and org.flatpak.Builder through your normal host setup if absent. They were already available here. From this checkout on the host:

```sh
flatpak run --filesystem="$PWD" org.flatpak.Builder \
  --user --disable-rofiles-fuse --force-clean --repo=flatpak-repo \
  build-flatpak com.nedrichards.Skyloom.json
flatpak install --user --reinstall "$PWD/flatpak-repo" com.nedrichards.Skyloom
flatpak run com.nedrichards.Skyloom --demo
mkdir -p dist
flatpak build-bundle flatpak-repo dist/com.nedrichards.Skyloom-0.1.0-x86_64.flatpak com.nedrichards.Skyloom master
```

Do not delete flatpak-repo as part of routine build cleanup: an installation made from it uses that repository for updates. The `--reinstall` step is necessary for an existing installation from a local repository; a plain install can skip an older installed revision.

The Builder downloads the checked source wheels and verifies SHA-256 hashes, then pip installs offline with no dependency resolution. Rebuild with `--disable-download` after sources are cached to verify the offline application build. Runtime installation itself is a separate prerequisite. The current wheel set is x86_64/cp314; regenerate it for other architectures.

This agent environment needs `flatpak-spawn --host` before host Flatpak commands because nested namespaces are restricted. That prefix is not needed in a regular host terminal. Running the SDK as a bare runtime produced Glycin loader sandbox failures here; the installed application and its decoder tests worked. Do not disable Glycin's sandbox to work around development configuration.

An SDK Meson build with the application's actual decoder sandbox and installed dependencies was also verified:

```sh
flatpak run --user --devel --command=sh --filesystem="$PWD" com.nedrichards.Skyloom \
  -c 'cd "$1" && meson setup build-runtime --prefix=/app && meson compile -C build-runtime && meson test -C build-runtime --print-errorlogs' sh "$PWD"
```

## Runtime checks

The combined local gate is `./scripts/check.sh` (pinned development tools plus an installed app are required). Run the native source command above before installation, and the following installed/runtime commands after it:

```sh
./scripts/test-in-flatpak.sh
./scripts/smoke-flatpak.sh
flatpak info --user --show-permissions com.nedrichards.Skyloom
flatpak run --user --command=sh --filesystem="$PWD:ro" \
  --env=PYTHONPATH="$PWD/src" com.nedrichards.Skyloom \
  -c 'python3 "$1/scripts/keyring-self-test.py"' sh "$PWD"
```

The first script executes the checkout's tests against the installed runtime/dependencies. The smoke script runs the **installed application's own code**, with only its fixture screenshot destination exposed. Its --demo requirement prevents account capture. It asserts actual window sizes, waits for rendered frames, navigates pages, tests reaction rollback/debounce and draft restoration, and publishes only to the in-memory demo backend. Screenshots are GTK-rendered application captures, not desktop captures. This display is 1503 logical pixels wide, so a native 1600-pixel screenshot could not be produced.

The keyring test uses a separate application attribute and an invalid dummy value, never an actual account session. Do not attach account databases, logs, credentials or live-account screenshots to issues.

## Refresh Python dependencies

In a Python 3.14 environment on the target architecture, resolve intended versions, update requirements.lock, download only binary wheels into wheels/, then run:

```sh
.venv/bin/pip download --only-binary=:all: -r requirements.lock -d wheels
.venv/bin/python scripts/generate-dependencies.py
```

The generator checks each local wheel against its PyPI digest and rewrites python-dependencies.json and requirements-hashed.lock. Review the package/version delta before rebuilding. wheels/ is disposable and ignored; the manifest contains stable upstream URLs and hashes. Do not copy an unrelated environment's pip freeze into the production lock.

## Human acceptance before public release

[ROADMAP.md](ROADMAP.md) is the canonical list of outstanding release gates and optional features.

Launch normally and enter a dedicated app password directly into the app. Check sign-in, relaunch/restore, pagination, thread/back position, like/unlike, repost/undo, nested reply, text/image/quote posts with alt text, saved feeds, follow/unfollow, mute/block, notifications/read, search pagination and sign-out/relaunch. Verify the file portal, keyboard-only journey and Orca; review large text and high contrast with real interaction as well. The automated smoke also passed with ADW_DEBUG_HIGH_CONTRAST=1 and SKYLOOM_SMOKE_FONT="Adwaita Sans 16". These require human interaction and/or credentials and are not replaced by the demo smoke.

No public repository or homepage has been configured. AppStream therefore reports a missing homepage warning; do not invent a URL to silence it. Review moderation policy and public metadata before publishing. The maintainer has selected the current name, application ID and Open Loom artwork. No Flathub submission or public release was performed.

## Code quality and Python support

Python 3.14 is the minimum supported interpreter, enforced by Meson and project metadata. Ruff 0.17.2 is enforced by configuration and pinned in requirements-dev.lock. Run `./scripts/lint.sh` for stable and selected preview lint, formatting, SyntaxWarning-as-error compilation and shell syntax. All application, test and helper Python is included. See [LINT_POLICY.md](LINT_POLICY.md) for exact rules and exceptions and [PYTHON_314_AUDIT.md](PYTHON_314_AUDIT.md) for reviewed language/library features and measured model allocations.

Native metadata checks additionally include `glib-compile-schemas --strict --dry-run data`. Strict AppStream validation still exits 3 for the missing public homepage; this is an open metadata warning. No static type checker or remote CI is configured. `./scripts/check.sh` provides the reproducible local integration gate; [TESTING.md](TESTING.md) explains its scope.

Run native widget tests and GUI smoke sessions sequentially. The paging widget tests use GTK frame callbacks; presenting another test window over them can suspend those callbacks and cause timing failures. The current verified count is recorded in [BUILD_ENVIRONMENT.json](BUILD_ENVIRONMENT.json). Run the suite separately from smoke. This is a test-orchestration limitation, not a headless test guarantee.

Current Wayland full-suite runs can time out waiting for frames in the feed
position fixtures, with either the default renderer or Cairo. Explicit X11/Cairo
is the selected functional test environment for the responsive-sidebar change;
intermittent standalone conversation-focus failures remain separately tracked in
the roadmap. To select
that environment without changing assertions or product renderer preferences:

```sh
flatpak run --user --socket=x11 --nosocket=wayland \
  --env=GDK_BACKEND=x11 --env=GSK_RENDERER=cairo \
  --command=python3 --filesystem="$PWD:ro" --env=PYTHONPATH="$PWD/src" \
  com.nedrichards.Skyloom "$PWD/scripts/runtime-tests.py" --tests "$PWD/tests"
```

Use `--env=PYTHONPATH=/app/share/skyloom` in the same command to test the installed
code. Supplying `GDK_BACKEND` only in the host environment is insufficient:
Flatpak filters it, so use its explicit `--env` option. The sidebar frame tests
also pass in the normal desktop session; this does not make a timed-out full
Wayland suite a pass. See the delivery report for the individual results.

The GUI smoke now activates feed and quoted tiles, checks compact padding at 480/800 pixels, retries a failed conversation branch, loads deeper replies and scrolls up to load ancestors. Unit tests exercise native GTK activation/keyboard/label controllers and selection cancellation. These tests use only invented records; they do not prove physical touchscreen or authenticated-service behaviour.


## Native input regression

Run this separately from other GUI tests, on a desktop with X11/Xwayland and the GNOME SDK. It targets only its unique invented-data window title and uses memory preferences. Keep the window unobstructed; it needs input focus. The driver keeps its Xwayland client alive after releasing each key so an early disconnect cannot leave a virtual key held. The runner also releases deliberately held keys on failure.

```sh
flatpak run --user --devel --socket=x11 --nosocket=wayland \
  --env=GDK_BACKEND=x11 --env=GDK_SCALE=1 \
  --env=SKYLOOM_KEYBOARD_DRIVER="$PWD/scripts/keyboard-event.py" \
  --filesystem="$PWD:ro" --command=python3 com.nedrichards.Skyloom \
  -m skyloom --demo --keyboard-test
```

This runs the installed application's keyboard runner. For source development also provide PYTHONPATH="$PWD/src" and GSETTINGS_SCHEMA_DIR="$PWD/build-runtime/data" through Flatpak --env options after compiling the current schema. The checked sequence covers real arrows/J/pages/End, held Enter, Back position, top/Undo, F6 panes, destination shortcuts, search typing, native editor Undo, help/menu Escape and notification movement at wide/narrow sizes. It does not prove physical touch, Orca or authenticated actions. Double-click and pull state are covered by native controller/pure-state regressions; synthetic pointer delivery remains unreliable on this desktop.

The extended GUI smoke also checks connection/power gates, immediate feed insertion with a stable reading anchor, Go to top/position Undo, failure backoff and explicit metered refresh. Suspend elapsed-time decisions use injected clocks, and the supported runtime dispatches/closes a real BOOTTIME timerfd. Actual laptop suspend/network transitions still need a human hardware check.


Profile/search scrolling regressions cover native section-header ownership, empty/repopulated content, complete biographies, compact identity, deep-scroll return, top/Undo anchors and search focus after recycling. Installed smoke captures expanded/compact profiles at 800/480 pixels and scrolls long image descriptions; high contrast/large text runs the same checks. Only the ListView owns the page scroll adjustment, preserving virtualisation and post/footer indices.

## Performance profiling

[PERFORMANCE.md](PERFORMANCE.md) gives installed native frame/presentation, CPU, memory and row/media measurements with separate reading, editing/notifications, narrow-window, reduced-motion, startup and control configurations. Run profiling sequentially with tests/GUI smokes. Keep captures in ignored `build*/` paths, use only the isolated demo runner, and retain tail latency and unachieved frame-budget goals in reports.


Reading-cache regressions use invented accounts and temporary SQLite databases. `test_feed_state.py` checks thousands of records, age/count eviction, protected windows, account isolation, cursor completeness and bounded reconciliation. Native startup/controller cases restore a 240-post reading window offline, apply the restart order, preserve subsequent live order, verify native gap retry controls, cancel scroll corrections after new input, retain small visible row fragments exactly and checkpoint immediately before opening a conversation. Service contracts verify page caching and stale-save rejection across sign-out/re-sign-in.


## Focused installed checks

The required native gate rejects unexpected skips. Run `./scripts/test-in-flatpak.sh --installed` after installation. Isolate GUI scenarios with `flatpak run com.nedrichards.Skyloom --demo --smoke-test OUTPUT --smoke-scenario preferences` (or navigation/profile/search/labels/conversation/paging/refresh/offline). Preserve the full journey as a separate gate.

Run the distinct-image residency experiment in separate processes inside the installed decoder sandbox: `python3 scripts/benchmark-media-residency.py --mode retain-all --output BEFORE.json` and `--mode viewport --output AFTER.json`, exposing the source/output paths as in PERFORMANCE.md. It generates invented PNGs and measures native Picture references, conservative pixel estimates and process peak RSS; retain-all simulates prior ownership and is not an old installed-binary comparison. Use the versioned performance runner/comparator for matched work/frame checks; missing or compositor-throttled samples must not be reported as a pass.

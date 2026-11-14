# Development

Use Python 3.14 and GNOME 51. Native dependencies and build requirements are in
`meson.build` and `com.nedrichards.Skyloom.json`; Python versions and hashes are
in the lockfiles and `python-dependencies.json`.

The current atproto pin is 0.0.74. Review upstream release notes and generated
model contracts before upgrading. Keep `pyproject.toml`, runtime/development
locks and the generated wheel hashes consistent; `pip check` verifies the
resolved environment. SDK boundary tests cover unknown records, extension-field
round trips and typed single-page access.

## Native build

Install the native GI libraries, Meson and Ninja, then run:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-dev.lock
PATH="$PWD/.venv/bin:$PATH" meson setup build --prefix="$PWD/local-install"
meson compile -C build
meson test -C build --print-errorlogs
glib-compile-schemas data
GSETTINGS_SCHEMA_DIR="$PWD/data" PYTHONPATH="$PWD/src" .venv/bin/python -m skyloom --demo
```

Meson selects Python at setup time. Use a fresh build directory when changing
interpreters. A Python environment without GI cannot validate the native UI.

## Flatpak

Install `org.gnome.Platform//51`, `org.gnome.Sdk//51` and
`org.flatpak.Builder`. From the checkout:

```sh
flatpak run --filesystem="$PWD" org.flatpak.Builder \
  --user --disable-rofiles-fuse --force-clean --repo=flatpak-repo \
  build-flatpak com.nedrichards.Skyloom.json
flatpak install --user --reinstall "$PWD/flatpak-repo" com.nedrichards.Skyloom
flatpak run com.nedrichards.Skyloom --demo
mkdir -p dist
flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
  flatpak-repo dist/com.nedrichards.Skyloom-0.1.2-x86_64.flatpak com.nedrichards.Skyloom master
```

Keep `flatpak-repo/`: local installations use it for updates. After caching
sources, repeat the Builder command with `--disable-download` to check the
offline build. Wheel sources are pinned for x86_64 and aarch64/cp314; `only-arches` filters native wheels.

In an agent sandbox that cannot create nested Flatpak namespaces, execute these
commands through `flatpak-spawn --host` if permitted. A regular host terminal
does not need that prefix. Keep the image decoder sandbox enabled; use the
installed application environment rather than a bare SDK for decoder checks.

Run the [test gates](TESTING.md) after installation. Outstanding release work is
in [ROADMAP.md](ROADMAP.md).

## Updating Python dependencies

Resolve the intended versions in Python 3.14 on the target architecture and edit
`requirements.lock`, then run:

```sh
.venv/bin/pip download --only-binary=:all: -r requirements.lock -d wheels
.venv/bin/python scripts/generate-dependencies.py
```

The generator verifies wheel digests against PyPI and updates
`python-dependencies.json` and `requirements-hashed.lock`. Review the dependency
delta and rebuild. Keep downloaded wheels out of Git. Lint settings belong in
`pyproject.toml`; development tools are pinned in `requirements-dev.lock`.

## Native ARM64 release builder

The manual `Build ARM64 Flatpak` GitHub Actions workflow uses an
`ubuntu-24.04-arm` runner and GNOME 51. Dispatch it with an existing version tag.
It checks out that immutable application source, verifies the dependency versions
match the builder's pins, and supplies the checked multi-architecture wheel
manifest. This permits building 0.1.2 without moving its existing tag.

The job builds and installs an aarch64 bundle, verifies the native architecture,
version and installed Python source parity, runs the strict native test gate on
X11/Cairo and an installed navigation smoke, then uploads the bundle, checksums
and application/tooling commit provenance as a short-lived Actions artifact.
Release-asset publication stays a separate reviewed maintainer action.

For dependency updates, download the exact requirements for both CPython 3.14
architectures into `wheels/` or architecture subdirectories before regenerating.
The generator checks PyPI digests, rejects incomplete architecture sets, ignores
superseded versions and emits the shared source manifest and multi-hash lock.

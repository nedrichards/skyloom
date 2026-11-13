# Development

Use Python 3.14 and GNOME 51. Native dependencies and build requirements are in
`meson.build` and `com.nedrichards.Skyloom.json`; Python versions and hashes are
in the lockfiles and `python-dependencies.json`.

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
flatpak build-bundle flatpak-repo dist/com.nedrichards.Skyloom-0.1.0-x86_64.flatpak com.nedrichards.Skyloom master
```

Keep `flatpak-repo/`: local installations use it for updates. After caching
sources, repeat the Builder command with `--disable-download` to check the
offline build. The wheel set currently targets x86_64/cp314.

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

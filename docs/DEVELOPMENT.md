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

## Hosted validation and releases

Every application check runs on native x86_64 (`ubuntu-24.04`) and aarch64
(`ubuntu-24.04-arm`) runners, using GNOME 51. `CI` runs on pushes to main,
pull requests and manual dispatch. Fast jobs install the locked Python 3.14
development environment, check lint and dependency consistency, test maintenance
guards and run checksum-pinned actionlint. The shared `native.yml` workflow
uses the official Flathub GNOME 51 build container (pinned multi-architecture
image digest) and SHA-pinned Flatpak Builder action. Flatpak and its runtimes
belong to that container; workflows do not install Flatpak on the Ubuntu runner
or change runner kernel settings. Inside the container it builds, exports and
installs a Flatpak, proves installed architecture/version and
Python source parity, then runs source tests, installed tests and demo smokes
sequentially. Unexpected skips fail the native gate.

Download installable bundles through the job summaries. Filenames identify the
built commit, including GitHub's merge commit for pull requests; `BUILD_INFO`
records application and tooling commits. Diagnostic artifacts contain logs,
named test failures and an offline visual contact sheet (`index.html`). Extract
the whole artifact before opening it. Artifacts expire after 14 days. Preview
bundles use the production application ID: installing one replaces that local
installation. Restore the published bundle after review if needed.

`Dependency health` checks runtime/SDK support, published wheel digests, newer
PyPI versions and vulnerability advisories weekly and when dependency inputs
change. Version differences are information; published advisories, unavailable
runtimes, EOL notices and inconsistent pins fail the job. Transport errors remain
visible failures rather than a clean health report. Dependency updates remain
reviewed changes across all locks and both architectures; the checker never
rewrites production pins. Dependabot groups updates to SHA-pinned Actions.
Review build-container digest updates manually with both native builds. The
container supplies Xvfb and Weston; two checksum-pinned Openbox/xcompmgr source
archives supply the composited X11 test session. They are built only in the
disposable CI container and are not bundled with Skyloom.
An anonymous Docker volume holds the container's preinstalled Flatpak state and
runtime updates, avoiding OSTree cross-filesystem updates through image layers.

`Extended compatibility` runs weekly or manually on both architectures. It runs
1,000 generated cases per boundary test, probes the newest atproto with other
runtime versions constrained to the production lock, and runs a separate advisory
Wayland/default-renderer check under headless Weston. The SDK probe installs into
a disposable overlay and records its resolved versions; an incompatible resolver
result is a probe failure. These jobs do not gate PRs, but their failures remain
visible in the scheduled workflow. Required functional tests use composited
X11/Cairo. Neither renderer on hosted hardware establishes desktop performance.

Dispatch `Prepare release Flatpaks` from the default branch with an existing
`vX.Y.Z` tag. The workflow resolves that tag once and builds the same immutable
application commit on both architectures. The tag must match the application
version. Tooling may supply the current multi-architecture wheel manifest and
hash lock for incomplete legacy packaging only when the runtime pins are
byte-identical, preserving support for
the existing 0.1.2 tag; any overlay is recorded in each `BUILD_INFO`. Packaging
also excludes disposable CI reports from the source input.

Both architectures must pass before the workflow attests the bundles and their
build information, then creates a draft release with checksums. Disable
`create_draft` to rebuild an existing release into Actions artifacts. Existing
releases are never overwritten, and publication remains a manual maintainer
action. The single tag-resolution and draft-assembly jobs run once; application
builds, tests, probes, reports and attestations run on both architectures.

Verify downloaded release assets with `sha256sum --check SHA256SUMS` and, using
GitHub CLI, `gh attestation verify BUNDLE.flatpak --repo nedrichards/skyloom`.
Verify the accompanying `BUILD_INFO` the same way to inspect the application
commit and packaging overlay. Attestation provenance identifies the release
workflow/tooling commit; it does not imply live-service or human acceptance.
See [GitHub's attestation documentation](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

Workflows use read-only repository permissions by default. Write/OIDC permissions
are confined to artifact attestation and draft creation; those jobs do not execute
application code. No account credentials or signed-in data belong in CI. There
is no privileged PR repair workflow. Automation using `GITHUB_TOKEN` must arrange
validation explicitly rather than relying on a push to retrigger CI; see
[GitHub's trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

For dependency updates, download the exact requirements for both CPython 3.14
architectures into `wheels/` or architecture subdirectories before regenerating.
The generator checks PyPI digests, rejects incomplete architecture sets, ignores
superseded versions and emits the shared source manifest and multi-hash lock.

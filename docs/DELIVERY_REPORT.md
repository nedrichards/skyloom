# Validation status

Live-account interoperability and human accessibility/hardware acceptance remain
open; see [ROADMAP.md](ROADMAP.md). Default-renderer scrolling has no accepted
matched performance baseline. Public homepage metadata remains a release gate.

## Repository cleanup — 13 November 2026

Removed historical documentation, benchmark output, generated icon previews and
routine smoke captures. Two invented-data showcase images remain. Shortened the
README and kept reusable development/profiling tools. No dead application code
was confirmed, so the large application modules remain intact.

Native tests share display setup and content/startup fixtures. Meson now uses
the strict runtime runner. A no-display run exposed a crash after GTK reported
successful initialisation without a default display; preflight now rejects that
state with exit status 2. The optional keyboard harness also rejects missing
injected input before testing selection.

The source suite passed 289 tests with zero skips before and after fixture
cleanup in host-launched GNOME 51 Flatpak under X11/Cairo. Lint, formatting,
compilation, shell syntax, desktop/schema validation and local documentation
links passed. Direct `check.sh` cannot cross the agent's nested Flatpak boundary;
its runtime stage was run separately through the host. Meson setup/compile, its full 289-test run with zero skips, and the offline
pinned Flatpak build/export/install passed. The installed keyboard harness hash
matches the source. The full installed demo GUI smoke passed with the normal
desktop renderer. The two showcase images were refreshed from that run and
visually checked; other captures remain ignored.

XTest reported successful sends but GTK received zero key events in both installed
and source keyboard runs. The corrected harness reports this as unavailable input,
not a failed J shortcut. Physical input acceptance remains open. GDK emitted a
skipped-frame warning during otherwise passing native runs; no performance claim
is made.

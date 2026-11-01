#!/usr/bin/env bash
# Read-only diagnostics for the Skyloom development environment. Makes no changes.
set -u
printf 'Skyloom environment check (read-only)\n'
printf 'Current directory: %s\n' "$PWD"
printf 'Date (UTC): '; date -u '+%Y-%m-%d %H:%M:%S' 2>/dev/null || true
printf 'Operating system: '; if [[ -f /etc/os-release ]]; then . /etc/os-release; printf '%s\n' "${PRETTY_NAME:-unknown}"; else printf 'unknown\n'; fi
printf '\nCommands:\n'
for cmd in git python3 meson ninja flatpak flatpak-builder appstreamcli desktop-file-validate blueprint-compiler pytest ruff; do
  if command -v "$cmd" >/dev/null 2>&1; then printf '  %-23s %s\n' "$cmd" "$(command -v "$cmd")"; else printf '  %-23s %s\n' "$cmd" 'not found'; fi
done
printf '\nGNOME runtime installed (if Flatpak present):\n'
if command -v flatpak >/dev/null 2>&1; then flatpak list --runtime --columns=application,branch 2>/dev/null | grep -E 'org\.gnome\.(Platform|Sdk)[[:space:]]+51' || printf '  GNOME 51 SDK/runtime not both detected\n'; fi
printf '\nPython GTK bindings: '
python3 - <<'PY' 2>/dev/null || true
try:
 import gi
 gi.require_version('Gtk', '4.0')
 gi.require_version('Adw', '1')
 from gi.repository import Gtk, Adw
 print('available')
except Exception as e:
 print(f'not available in current Python ({type(e).__name__}: {e})')
PY
printf 'Graphical session: XDG_SESSION_TYPE=%s WAYLAND_DISPLAY=%s DISPLAY=%s\n' "${XDG_SESSION_TYPE:-none}" "${WAYLAND_DISPLAY:-none}" "${DISPLAY:-none}"
printf '\nNo tools were installed and no account credentials were accessed.\n'

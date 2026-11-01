#!/usr/bin/env bash
# Reproducible local integration gate. GUI smoke is a separate sequential gate.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
./scripts/lint.sh
desktop-file-validate data/com.nedrichards.Skyloom.desktop
glib-compile-schemas --strict --dry-run data
./scripts/test-in-flatpak.sh "$@"
printf 'CHECK_PASS: lint, desktop entry, settings schema and native runtime tests\n'

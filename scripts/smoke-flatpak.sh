#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$root/screenshots/demo"
flatpak run --user --filesystem="$root/screenshots/demo" \
  com.nedrichards.Skyloom --demo --smoke-test "$root/screenshots/demo"

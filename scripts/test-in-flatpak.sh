#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
module_path="$root/src"
if [[ ${1:-} == --installed && $# == 1 ]]; then
    module_path=/app/share/skyloom
elif [[ $# != 0 ]]; then
    printf 'Usage: %s [--installed]\n' "$0" >&2
    exit 2
fi
flatpak run --user --command=python3 --filesystem="$root:ro" \
  --env=PYTHONPATH="$module_path" com.nedrichards.Skyloom \
  "$root/scripts/runtime-tests.py" --tests "$root/tests"

#!/usr/bin/env bash
# Fast, offline first-party checks. Native/runtime gates are documented separately.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
python_bin=${SKYLOOM_PYTHON:-"$root/.venv/bin/python"}
"$python_bin" -m ruff check src tests scripts design
"$python_bin" -m ruff check src tests scripts design --preview --extend-select PLW1514,RUF056,shared-clock-mock
"$python_bin" -m ruff format --check src tests scripts design
"$python_bin" -Werror::SyntaxWarning -m compileall -q -f src tests scripts design
for script in scripts/*.sh; do
    bash -n "$script"
done
printf 'LINT_PASS: stable Ruff, selected preview rules, formatting, compilation, shell syntax\n'

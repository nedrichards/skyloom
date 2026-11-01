# Lint policy

Reviewed 27 October 2026. Run `./scripts/lint.sh` after installing `requirements-dev.lock`. Use `SKYLOOM_PYTHON=/path/to/python` to select another development environment. The script is offline and does not modify sources.

## Current Ruff configuration

`pyproject.toml` targets Python 3.14 and requires exactly Ruff 0.17.3, matching the development lockfile. The stable rules apply to **all** Python under `src`, `tests`, `scripts` and `design`.

| Rules | Purpose |
| --- | --- |
| `E`, `W`, `F`, `I` | Syntax/style, undefined names, whitespace and import order |
| `UP`, `FURB`, `C4`, `PIE`, `SIM`, `RET`, `RSE`, `FLY` | Modern Python, comprehensions and clearer control flow/string construction |
| `B`, `A`, `RUF`, `YTT` | Common bugs, shadowed built-ins, Ruff-specific correctness and version checks |
| `S`, `BLE`, `DTZ` | Security patterns, broad exception catches and timezone handling |
| `ASYNC`, `PERF`, `SLOT` | Async pitfalls, avoidable work and slotted subclass consistency |
| `LOG`, `ICN`, `ISC`, `EXE` | Logging, import conventions, accidental string concatenation and executable scripts |
| `PGH`, `T10` | Precise suppressions, invalid ignores and accidental debugger statements |
| `TRY201`, `TRY203`, `TRY400`, `TRY401` | Exception re-raising and logging mistakes |

The second command in the script adds only preview rules `PLW1514` (explicit file encodings), `RUF056` (redundant falsy dictionary defaults) and `shared-clock-mock` (patch only the consumer’s clock reference, keeping other tasks and threads on the real clock). `explicit-preview-rules = true` prevents selected families from silently enabling all their preview rules. Ruff's formatter runs in stable mode. See the upstream [rule catalogue](https://docs.astral.sh/ruff/rules/) and [preview configuration](https://docs.astral.sh/ruff/preview/).

## Deliberate exceptions

- `E501` remains ignored: the formatter wraps code to 100 columns where practical; long protocol URLs and user-facing prose need not be split artificially.
- The typographic apostrophe `’` is permitted in English copy. Other confusable checks remain active.
- `S101` is allowed only in tests and the demo-only GUI smoke runner. Smoke refuses optimized Python, which would disable assertions. Production wheel and dummy-keyring verification use explicit exceptions.
- Local, rule-specific `BLE001` suppressions retain libsecret redaction, SDK-to-GTK error sanitization and the smoke runner's failure boundary. Sign-out additionally suppresses `S110`: offline server revocation must not prevent local sign-out, and logging that exception could disclose token-bearing requests. Existing contract tests cover revocation failure and local cleanup.
- The isolated native-input runner suppresses `S603` for its fixed interpreter, exact-title test driver and bounded subprocess calls; it never uses a shell or real account. The checksum regression test suppresses `S603` for a fixed Python interpreter/program with generated fixture paths; no shell is used. The benchmark suppresses `FURB162` only on the former timestamp implementation used as a timing control.

The broader `TRY` family was trialled. Rules against descriptive exception messages or raising inside a protected operation add churn to user-facing recovery paths here. Annotation/docstring mandates and arbitrary complexity limits were not added. Ruff is not a static type checker; mypy/Pyright are not configured. GI integration and callback correctness are exercised in the actual runtime rather than represented as a type-checking claim.

## Other gates

`./scripts/lint.sh` also checks formatting for every helper script, compiles all first-party Python with `SyntaxWarning` promoted to an error, and runs `bash -n` on every shell script. Shell syntax checking is not ShellCheck semantic analysis; ShellCheck is not configured.

The authoritative integration gate is Meson/unittest inside the GNOME 51 SDK with the installed app's dependencies and decoder sandbox. Additional packaging gates are `desktop-file-validate`, `glib-compile-schemas --strict --dry-run data`, AppStream validation, a clean offline Flatpak build/export/install, and the installed demo GUI smoke run. Commands are in [DEVELOPMENT.md](DEVELOPMENT.md).

AppStream still reports `url-homepage-missing` and exits 3. A maintainer-supplied public project URL is needed; none is invented. This is a recorded packaging warning, not a passing strict AppStream check. Upstream GI asyncio-policy and HTTPX upload deprecations remain visible in tests.

No hosted CI execution, static typing, live-account interoperability or human accessibility acceptance is implied by these gates.

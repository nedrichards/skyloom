# Python through 3.14: implementation review

Reviewed 27 October 2026 against first-party imports and the official release notes. The installed GNOME 51 Flatpak supplies CPython **3.14.9**, with the GIL enabled and no available JIT. `compression.zstd` is available. These are inspected runtime facts, not assumptions about every Python installation. Project metadata, Meson and Ruff now require/target 3.14; development requirements already pin compatible wheels.

## Adopted

| Feature | Application and evidence |
| --- | --- |
| Slotted dataclasses (3.10) | Author, Media, Post, Page, Notice and Attachment retain immutable value semantics while avoiding per-object dictionaries. Nested quote/media cache round trips and reaction replacement are tested. [Dataclasses reference](https://docs.python.org/3.14/library/dataclasses.html) |
| Direct ISO timestamps with `Z` (3.11) | `relative_time` passes timestamps directly to `datetime.fromisoformat`, removing an allocation on every formatted timestamp. Tests cover fractional seconds, UTC, offsets, future values, malformed and timezone-free input. [Datetime reference](https://docs.python.org/3.14/library/datetime.html#datetime.datetime.fromisoformat) |
| Streamed file hashing (3.11) | Wheel verification uses `hashlib.file_digest` instead of reading the entire wheel into a bytes object. Checksum mismatches raise under optimized Python too; empty wheel sets preserve existing locks. [Hashlib reference](https://docs.python.org/3.14/library/hashlib.html#hashlib.file_digest) |
| `type` aliases (3.12) | `SmokeStep` names the GUI runner's callable contract. Every step explicitly reports completion or a bounded wait; recursive widget searches explicitly report absence. [3.12 release notes](https://docs.python.org/3.14/whatsnew/3.12.html) |
| Linux timerfd (3.13) | The native refresh monitor registers a nonblocking `os.timerfd_create(CLOCK_BOOTTIME)` with GLib, counts suspended time without waking hardware, and closes the source/descriptor while ineligible. Runtime dispatch/cleanup and injected resume clocks are tested. [Timer descriptors](https://docs.python.org/3.14/library/os.html#timer-file-descriptors) |
| Concrete `asyncio.EventLoop` (3.13) | The worker constructs its platform loop directly. Shutdown is an async operation inside that loop, including empty-task draining, client cleanup, async generators and executor shutdown. Tests exercise empty and pending shutdown and main-thread completion. [Event-loop reference](https://docs.python.org/3.14/library/asyncio-eventloop.html) |
| Deferred annotations (3.14) | Recursive `Post` annotations no longer need quotes or a future import. Runtime type-hint resolution is tested. [3.14 release notes](https://docs.python.org/3.14/whatsnew/3.14.html#deferred-evaluation-of-annotations) |
| Thread `context=` (3.14) | The network thread starts with an explicit empty Context; submitted requests still propagate their own context. A runtime test verifies both behaviours. [Thread reference](https://docs.python.org/3.14/library/threading.html#threading.Thread) |
| Exception lists (3.14) | The pinned formatter uses the supported parentheses-free exception-list syntax where it fits on a line. No manual syntax-only rewrite was needed. [3.14 release notes](https://docs.python.org/3.14/whatsnew/3.14.html) |
| Specific unittest assertions (3.14) | `assertStartsWith` makes the facet-prefix assertion direct and gives useful failure diagnostics. [Unittest reference](https://docs.python.org/3.14/library/unittest.html#unittest.TestCase.assertStartsWith) |

Other quality fixes found by the audit: explicit UTF-8 fixture/lock IO, bounded dependency metadata requests, isolated temporary demo drafts with shutdown cleanup, built-in-safe names, tuple suffix checks, and narrowly documented error-redaction exceptions. Existing UTC constants, native generic/union annotations, asynchronous IO and parenthesized context managers already fit the supported interpreter.

## Measured effects

Synthetic fixture benchmark, x86_64 installed Flatpak, CPython 3.14.9. The same 1,000 fabricated posts each contain a fresh author and two media records; strings are shared. Seven allocation samples use tracemalloc after warming imports, with GC between samples.

| Measurement | Before | After |
| --- | ---: | ---: |
| Median retained Python allocations | 698,704 bytes | 514,704 bytes |
| Median mapping time / 1,000 posts | 24.42 ms | 24.34 ms |

The allocation reduction is **184,000 bytes / 26.3%** in this model workload. Mapping throughput is effectively unchanged; no whole-app speed or memory claim is made. A paired timestamp microbenchmark, alternating order over ten samples of 100,000 parses after warm-up, measured 25.13 ms with replacement versus 15.23 ms parsing directly. Timing varies with CPU load.

Reproduce current measurements using the checked-in benchmark with the source tree mounted read-only:

```sh
flatpak run --user --command=sh --filesystem="$PWD:ro" \
  --env=PYTHONPATH="$PWD/src" com.nedrichards.Skyloom \
  -c 'cd "$1" && python3 scripts/benchmark-models.py' sh "$PWD"
```

The benchmark retains the old timestamp operation as an explicitly lint-suppressed control. The model baseline was captured before adding slots; the current command measures the current source.

## Reviewed without introducing unnecessary machinery

| Feature group | Decision for this application |
| --- | --- |
| Template strings | Existing Pango escaping is tested. T-strings require an explicit renderer and do not themselves make markup safe; a new engine would add abstraction around one link-rendering site. [Template reference](https://docs.python.org/3.14/library/string.templatelib.html) |
| Subinterpreters, interpreter pools | No CPU-bound Python pipeline justifies transferring model/state across interpreters or proving native extension isolation. GTK remains on its main thread. [Executor reference](https://docs.python.org/3.14/library/concurrent.futures.html) |
| Free threading, JIT, tail-call interpreter | Interpreter build choices belong to the runtime. Do not add unsupported flags, rebuild CPython, assume native-extension safety or claim an unmeasured speedup. [3.13 notes](https://docs.python.org/3.14/whatsnew/3.13.html), [3.14 notes](https://docs.python.org/3.14/whatsnew/3.14.html) |
| TaskGroup, exception groups, eager tasks | Independent GUI requests need independent cancellation. Shutdown intentionally drains all canceled tasks. Eager execution would change ordering without an identified benefit. Existing SDK/network deadlines remain. [Async task reference](https://docs.python.org/3.14/library/asyncio-task.html) |
| Async introspection, external debugger, monitoring | Useful development diagnostics for future stalls; no production polling or debugger endpoint is needed. Never capture real session locals in diagnostics. [3.14 notes](https://docs.python.org/3.14/whatsnew/3.14.html) |
| Standard-library Zstandard | No direct compressed-cache requirement. Do not remove the separately pinned zstandard package used by HTTPX: it imports that package's distinct API. [Zstandard reference](https://docs.python.org/3.14/library/compression.zstd.html) |
| Path.info, Path.copy/move, Path.walk | No directory traversal hot path; attachment checks need fresh metadata and existing transaction/error behaviour. [Pathlib reference](https://docs.python.org/3.14/library/pathlib.html) |
| Executor.map buffersize, process-pool changes | No executor map or process pool is used. Existing request queue and image semaphore already bound concurrency. [Executor reference](https://docs.python.org/3.14/library/concurrent.futures.html) |
| map strict, batched strict, max-heaps | No aligned multi-iterable mapping, batch framing or priority heap to simplify. [Built-ins](https://docs.python.org/3.14/library/functions.html#map), [itertools](https://docs.python.org/3.14/library/itertools.html), [heapq](https://docs.python.org/3.14/library/heapq.html) |
| Placeholder/partial, copy.replace | Explicit callbacks and dataclasses.replace already express the relevant operations clearly. [Functools](https://docs.python.org/3.14/library/functools.html), [Copy](https://docs.python.org/3.14/library/copy.html#copy.replace) |
| UUID 6/7/8 | Account-scoped drafts and protocol record IDs have existing identities; switching formats has no demonstrated benefit. [UUID reference](https://docs.python.org/3.14/library/uuid.html) |
| Dataclass field docs/decorators, typing defaults | No generated schema/documentation or generic abstraction needs them. Keep annotations proportionate to interfaces. [Dataclasses](https://docs.python.org/3.14/library/dataclasses.html), [Typing](https://docs.python.org/3.14/library/typing.html) |
| F-string grammar, match | Existing formatting already uses modern f-strings. Rewriting simple branches as pattern matches has no demonstrated benefit. [3.12](https://docs.python.org/3.14/whatsnew/3.12.html), [3.14](https://docs.python.org/3.14/whatsnew/3.14.html) |
| REPL/help colours, argparse suggestions | Development benefits require no changes. This CLI has no subcommands/choice lists needing suggestion configuration. [Argparse](https://docs.python.org/3.14/library/argparse.html) |
| re, sqlite3 and file/byte API changes | Existing regexes avoid changed empty-boundary behaviour. Standard-library Unicode updates do not replace the pinned regex library’s grapheme segmentation. SQLite uses positional `?` values with tuples and explicitly closes connections. No new binary parser is needed. [Regex](https://docs.python.org/3.14/library/re.html), [SQLite](https://docs.python.org/3.14/library/sqlite3.html) |
| Runtime optimizations, GC, warnings | Accept the supported runtime defaults; do not tune GC from a synthetic model test. The early incremental GC was reverted in 3.14.5. Compilation checks reject SyntaxWarnings, including invalid finally control flow. Upstream deprecations remain visible. [3.14 notes](https://docs.python.org/3.14/whatsnew/3.14.html) |

The release-note review also covered changes in unused modules (calendar, ctypes/C API, email, HTTP servers, pdb, platform, SSL, tar/zip tooling, turtle, Windows and WebAssembly support). These need no first-party substitutions; runtime and SDK dependencies retain their own implementations. See the [complete 3.14 release notes](https://docs.python.org/3.14/whatsnew/3.14.html) for that inventory. No new dependency was required.

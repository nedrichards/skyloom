# Testing

Thread-position regressions cover separate conversations, cross-author branches,
parent/root fragments, bounded metadata eviction, malformed cycles and shared
mounted feed/search/quote pills without body replacement. Pointer-selection
regressions exercise sub-threshold jitter, deliberate drags returning near their
start, existing selections, Shift-click, double-click cancellation and unbind.
Native signal injection validates controller decisions; physical mouse/touch and
Orca acceptance remain separate human checks. GTK's documented
[drag threshold](https://docs.gtk.org/gtk4/method.Widget.drag_check_threshold.html)
supplies the movement tolerance rather than a hard-coded pixel distance.

Run native widget tests and GUI smoke sequentially on a desktop with GNOME 51. An occluded window can stop frame callbacks. Overflow-menu assertions open and close each popover once before waiting for the screenshot frame; repeatedly reopening it while capturing invalidates GTK snapshots. Assertions remain enabled in the demo smoke; optimised Python is rejected there. Every automated social record and screenshot is invented.

## Local integration gate

`./scripts/check.sh` runs pinned Ruff checks/formatting, SyntaxWarning-as-error compilation, shell syntax, desktop/schema validation and the checkout's test suite inside the installed Flatpak runtime. It is the local automation equivalent used in this checkout; hosted CI is not configured. Installation/build commands and the agent-to-host boundary are in [DEVELOPMENT.md](DEVELOPMENT.md).

The tests exercise Unicode limits/facets, defensive DTO mapping, bounded pagination/conversation traversal, session create/import/refresh and persistence failures, request cooldown, mutation rollback, post/reply/image serialization, draft retention, cache privacy/eviction/sign-out invalidation, real platform image decoding, worker main-thread dispatch, native widget/focus/scroll contracts and refresh policy/timerfd. Startup regressions render the actual window with synthetic async restore outcomes and memory preferences: fast/slow success, missing session, recovery/retry/manual sign-in, closing during lookup, delayed-spinner cancellation and native animations enabled/disabled. HTTP tests use a mock transport with the real SDK; they do not contact an account.

## Installed application gate

Run `./scripts/smoke-flatpak.sh` after installing the current build. It runs the installed application's code, navigating the real native widgets with fixture data. It checks feed/thread/reactions, draft save/restore/publish-to-demo, profile composition/compact title, search, menus, preference bindings and wide/narrow account settings, sign-out confirmation/cancel/focus/failure retry, notification read state, descriptions and label chips/explanations/preferences/hidden cards at 800/480 pixels, paging, refresh Show/Undo/backoff, cache-first feed switching, full-height search initial/loading/results/empty/error/retry/clear states at wide/narrow sizes, offline post/draft behaviour, and wide/narrow navigation allocation, exclusive overflow menus and F10 routing after hide/show. Native regressions also cover repeated sidebar transitions, resizing, newly created content menus and dismissal of hidden popovers.

Repeat separately with `ADW_DEBUG_HIGH_CONTRAST=1` and `SKYLOOM_SMOKE_FONT="Adwaita Sans 16"` passed through Flatpak `--env`. Screenshots are rendered GTK fixture windows in `screenshots/demo/`. No real account is captured.

The standalone `--keyboard-test` runner requires a working X11/Xwayland input-injection path and an unobstructed, focused invented-data window. Its current environment block and the remaining human accessibility/hardware checks are recorded in [DELIVERY_REPORT.md](DELIVERY_REPORT.md) and [ROADMAP.md](ROADMAP.md). Controller signal emission is not proof of physical input delivery.

## Packaging and release checks

Build with checked wheel hashes, rebuild without downloads after caching sources, export/install the Flatpak, run the installed module tests and demo smoke, compare installed source hashes, inspect permissions and create/hash the local bundle. The durable `flatpak-repo/` is separate from disposable Builder state. AppStream composition during export and strict metadata validation are distinct checks: strict validation currently reports the absent public homepage and is an open release gate.

The optional dummy-keyring script uses a separate test attribute and invalid synthetic value; it never reads account credentials. Never attach account databases, sensitive logs or real-feed screenshots to tests/issues. New changes must state which layer was tested; a mock, source run or successful build alone does not prove live-account behaviour.

## Startup fixture isolation

`tests/test_startup.py` exercises the real Window and root stack with a separate fixture application, memory preferences and synthetic async restore outcomes over temporary demo storage. It never creates a real Service or reads the account keyring. Frame traces assert saved-session launches never map Sign in, slow lookup alone triggers the delayed spinner, recovery remains distinct, and close/retry cancel delayed callbacks. A native stack test checks transitions with GTK animations enabled and disabled. Run this suite separately from other GUI sessions; the installed startup subset was also checked with 16-point Adwaita Sans and `ADW_DEBUG_HIGH_CONTRAST=1`.

Content-label regressions verify lazy media construction, default visibility, quote independence, row rebinds, synchronized mounted copies, native focus after Show/Hide, lazy popovers, post/author/profile scope, deduplication, custom/long values, bounded inline chips, exact clipboard copying and the preferences action. Installed fixture captures cover visible/hidden states and detail popovers in standard and high-contrast/large-text runs.

Conversation identity regression: repeated activation of the visible anchor, including before loading completes, must retain the same page, request and stack depth. Different anchors retain distinct Back steps; returning to the previous anchor does not reload it, and reopening after returning to the feed remains possible. The installed fixture smoke repeats activation after rendering and checks page identity, stack depth and scroll position.

Refresh-cascade regressions assert that repeated connectivity sync emits no list replacement or extra image requests, while reaction sensitivity updates; unchanged connection state does not requeue lists, and a changed metered preference still does. Additional checks cover avatar cancellation, cache rechecks after queued media obtains a slot, and feed metadata replacement retaining selection without reload. Local worker saturation and the server-429 cooldown remain separate error paths.

Conversation redesign regressions cover reverse/equal/offset/invalid timestamp ordering, causal subtrees, missing/blocked gaps, branch-local continuations, incremental older-sibling insertion, refresh retaining deeper messages/local reactions, shared visual/keyboard indices, exact cross-author feed reply activation, conservative same-author grouping, focused reaction restoration, logical loader focus/keyboard scope, completion isolation from another page, and scoped relationship/Return/Undo keys. The installed ordered fixture opens a feed comment on another author’s thread, loads its earlier branch, checks reading order, refreshes without dropping depth and verifies Back/deduplication; captures include 480/800 light/dark and high-contrast/large text.

Profile-layout fixture checks measure browser/filter centre-line alignment at ordinary width, allow natural wrapping when constrained, and check the own-profile pair at 480/800 with large text. They activate the footer profile card, verify bottom placement and a single Profile destination, retain stack depth on repeated activation and exercise F6 through the narrow sidebar overlay. The large-text check follows the actual SP-scaled breakpoint rather than assuming 800 pixels is always a wide layout.

Refresh regressions cover overlapping/disjoint head snapshots, the 250-post boundary and resumed real cursors; one model insertion for one arrival with existing object identities preserved; counter changes retaining body/media widgets and submitting no additional image jobs; top positioning after banner allocation; reduced-motion/cancellation cleanup; and immediate feed insertion retaining order/position, followed by Go to top/position-only Undo retaining refreshed data and real cursors. The installed full fixture smoke asserts stable reader/object identity before Go to top and after position-only Undo.

Run the separate installed performance pass described in [PERFORMANCE.md](PERFORMANCE.md) with animations enabled and with reduced motion. Native regressions cover shared image/texture identity, consumer cancellation and account generation isolation, lazy menu actions, and viewport-only media loading with close cleanup. Performance distributions retain tail outliers and distinguish missing samples from zero latency.

A native notification regression marks 100 rows read without item replacements, checks native subtitles and focus, and verifies that a changed reason still takes the full content-update path. The performance runner also covers actual demo reactions, editing/draft autosave, four previews, notifications/Mark seen, menus, Preferences, image viewing and offline/online sensitivity.

The performance/battery continuation adds native deadline, focus/IO resume, inactive paging, modern reduced-motion, power-saver, animation replacement/unmap and fixed-geometry feedback regressions. Viewer reaction changes pulse once; count updates and server acknowledgement do not. `performance-pass.py --idle-only` records quiet mapped/unmapped process CPU and context switches; these are activity proxies, not battery-energy measurements.

Card regressions measure real profile/chip allocations and GTK picks at 480/800 pixels, verify empty header space is outside the profile target and eliminate FlowBox cell focus stops. A native pointer-controller/keyboard sequence verifies cursor handoff without stealing focus, and child-control focus is distinct from row focus. Conversation refresh restores the profile focus key as well as reaction controls. Installed fixture captures exercise quiet/card/child focus states, light/dark and high-contrast/large-text layouts. Programmatic native focus and picks are not physical pointer/touch or Orca acceptance.

The earlier card pass ran all 153 source tests with the default renderer and all 153 installed functional tests with `GSK_RENDERER=cairo`, under X11. Repeated installed default-renderer runs intermittently time out awaiting native frames/focus; those failures remain recorded in DELIVERY_REPORT and ROADMAP. Cairo is a diagnostic functional check, not a replacement for default-renderer pacing, the installed visual smoke or physical-input acceptance. No product renderer setting is changed.

The upper-edge/overlay regressions check native damped animation progress/end, wheel coalescing and pass-through, modern/legacy motion settings, power saver, scroll-away/close cancellation and unchanged scroll geometry/model identity. Native Show-toast tests cover replacement, dismissal with keyboard fallback, no viewport resize/reposition, no repeated scroll announcements, page scoping and stale actions after close. The installed refresh smoke waits for the actual toast to be visible before capturing/clicking Go to top, then checks immediate insertion/top/object/cursor/position Undo/backoff behaviour. Separate peak/rest captures pause a real animation briefly to inspect the clipped translated snapshot; they are fixture visuals, not physical wheel/touch acceptance.

Controller fixtures explicitly supply window activity and establish native logical list focus before dispatch; inactive paging/peek cases change that input and emit the native activity notification. Demo GUI smoke likewise supplies active-window eligibility, as it already supplies automatic-refresh eligibility and demo connectivity. This avoids treating compositor activation as an incidental layout-test precondition. Widgets, snapshots, timers, models and native focus traversal remain real; physical activation/key/touch delivery is still an acceptance gate. Earlier installed failures with uncontrolled activity are retained in the delivery record.


## Required runtime and regression gates

`./scripts/check.sh` now uses `scripts/runtime-tests.py`: Python/runtime/display preflight, non-empty discovery and zero unexpected skips are required. `./scripts/test-in-flatpak.sh --installed` checks packaged modules instead of source. Optional host discovery remains useful but is not installed/native acceptance. Focus/controller tests assert logical within-window focus using GTK's `is_focus`; compositor activity is supplied explicitly where it is a policy input. Physical delivery and visible focus styling still require their own acceptance checks.

Request/lifecycle regressions cover queued old completion versus replacement, account/page retirement, cancelled filesystem work versus clear/re-sign-in, repeated-cancel secure persistence, conversation parent discovery followed by counter updates, stale Undo controls, bridge duplicates, header interruption and profile paging's request-versus-presentation ownership. Storage checks verify a bookmark-only update serializes no Posts and changes one SQL row, and migration cannot replace fresh indexed records with stale legacy payloads.

Use `--demo --smoke-test OUTPUT --smoke-scenario NAME` for navigation, profile, search, preferences, labels, conversation, paging, refresh or offline checks; `full` retains the complete journey. Each process uses temporary data/memory settings and restores scenario patches. Preferences additionally captures the native appearance chooser at 800/480 in light/dark. Run it separately with `ADW_DEBUG_HIGH_CONTRAST=1` and `SKYLOOM_SMOKE_FONT='Adwaita Sans 16'` for contrast/large-text coverage. GUI and performance sessions run sequentially.

`scripts/compare-performance.py BASELINE CANDIDATE` rejects mismatched workload/runtime/backend/renderer/motion/monitor configuration, failed workloads, missing metrics and fewer than 30 scroll frame-work samples. Deterministic work counts have zero default growth slack; relative timing/CPU/RSS budgets allow explicit measurement noise. `performance-pass.py --baseline BASELINE` invokes the same gate. A rejected or under-sampled run is not a passing performance result; preserve its report and diagnose the environment rather than loosening expectations to hide it.

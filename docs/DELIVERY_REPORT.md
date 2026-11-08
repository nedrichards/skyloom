# Delivery report

## Adversarial security review — 8 November 2026

Reviewed session persistence/refresh/sign-out, authenticated mutations, external
links/rich text, attachment preparation, media/cache boundaries and Flatpak
permissions/pinned sources. Three concrete issues were fixed:

- The SDK follows redirects and can adopt a PDS endpoint from session/DID data.
  Checking HTTPS only at sign-in allowed later plain-HTTP requests. A production
  HTTPX request hook now rejects HTTP and URL credentials before dispatch,
  including redirect hops; valid HTTPS servers and redirects still work.
- Unblock copied the collection from an untrusted viewer URI into an
  authenticated delete, allowing a forged post URI to delete a post instead.
  All removal actions now require the account DID, intended collection and
  valid record key. A PDS lookup verifies the record's subject/type/URI, and
  `swapRecord` binds deletion to its verified CID. This adds one lookup per
  removal. Already-removed records remain successful no-ops; failures keep
  existing rollback/retry behaviour and never automatically retry mutations.
- Attachment preparation bypassed account storage invalidation, allowing a late
  worker to recreate private upload copies after sign-out. It now uses the
  account IO lock and captured generation. Cleanup removes completed work and
  rejects queued stale work; closed/retired composer callbacks are ignored.

Original-source HTTP contract reproductions fail for the forged unblock URI,
session-discovered HTTP endpoint and redirect downgrade. The fixed SDK contract
suite passes 21 tests, including malformed/wrong-owner/wrong-collection URIs,
wrong subjects, concurrent-delete failure, missing-record recovery and all five
redirect statuses. Native image tests exercise running/queued cleanup races and
late picker/preparation callbacks with invented data. The fixture's HTTP failure
selector was renamed so it no longer shadows unittest's assertion failure method.

The final installed GNOME 51 X11/Cairo suite passed **279 tests with zero skips**.
Offline pinned Flatpak build/export and local reinstall succeeded; all four
changed production modules match the installation byte for byte. Permissions
remain network/display/GPU/IPC and Secret Service only. `./scripts/check.sh`
passed lint, desktop metadata and schema checks before the known nested Flatpak
instance-allocation failure; the native suite above ran through the host route.
The installed full GUI smoke passed sequentially in normal styling and with
high contrast/16-point text, covering 480/800/1280-pixel layouts, composer/images,
draft recovery, reactions/rollback, navigation, sign-out recovery, conversations,
refresh and offline behaviour. Both composer captures were visually inspected.
GDK frame-timing warnings remain visible; these functional runs are not frame
pacing measurements. Captures and logs are in ignored `build-security-review/`.

No real credentials, account mutations or personal feed data were used. Human
live-service, physical input, Orca and default-Wayland acceptance remain open.
This is a source/contract/native review, not a claim that upstream dependencies
or all possible deployments have been independently security-certified.

## Maintenance checkpoint — 8 November 2026

The maintainer reports that the conversation scrolling changes work well and
substantially improve the experience. Some visual disturbance remains when new
items arrive during momentum scrolling in a long thread; this is recorded in
[the roadmap](ROADMAP.md), and seamless insertion is not claimed. This closes the
current optimisation pass; further investigation remains roadmap work.

Disposable build/export outputs, temporary source baselines, fixture captures and
interpreter/test caches were cleaned up for publication. Reviewed benchmark
scripts, aggregate results and regression tests remain versioned. Original
maintainer-supplied Sysprof captures remain local and ignored; reusable development
dependencies are retained. Earlier sections record evidence and limitations at
their delivery date, including outputs that have since been removed.

## Conversation loading and momentum — 8 November 2026

Conversation request completion previously restored the position saved before
the network request, after the view had already restored its newer position.
An invented delayed-response regression reproduces this duplicate restoration
with the old controller and passes with the new one. Completion now uses only
the current anchor. Appends below it and busy-only updates issue no positioning
request; stationary insertions before it correct the pixel offset without an
initial `scroll_to` reveal. Recent input-led kinetic scrolling suppresses
background viewport/focus corrections, while explicit navigation keeps its
normal behaviour and cancels pending corrections.

Loading/error controls update in place. Status-only changes reuse decorated
posts without projecting the conversation or rebuilding its post metadata.
Conversations use their branch geometry exclusively, disabling the competing
generic feed-end pager. Speculative reply loading follows reading direction;
the three-request budget renews when the first visible post changes. The single
in-flight request, 250-post cap, connection/activity/power restrictions, account
guards and explicit error recovery remain in force.

Native regressions exercise delayed network completion after scrolling, busy
control identity/focus, absence of scroll requests for appends and active scroll,
generic-pager exclusion, directional lookahead and budget renewal. The delayed
fixture uses an invented author without follow state. There is no follow-state
branch in the service loading path; colder caches exposing asynchronous changes
more often is an inference, not a reproduced live-account finding.

The final installed GNOME 51 X11/Cairo suite passed **270 tests with zero skips**.
An earlier installed run failed the new delayed-response test; that fixture lacked
an explicit check that native scrolling had passed the insertion branch. It now
waits for that visible precondition and retains its single-restoration, URI and
pixel-offset assertions. Source suites passed 270 tests before the final explicit
input reset, which the installed suite covers. Lint, desktop metadata and schema
checks passed. `./scripts/check.sh` reaches the known nested Flatpak instance
allocation failure; the native gate was instead launched through the host.
Offline pinned build/export and local reinstall succeeded.

The installed full X11/Cairo GUI smoke passed, including earlier/deeper/retry
conversation loading, Back, refresh/Undo and automatic paging. The normal
800-pixel invented conversation capture was visually inspected. Captures remain
in ignored build paths. GDK frame-timing warnings remain visible; functional
smokes are not frame-pacing measurements.

The installed high-contrast/16-point conversation scenario also passed at 800/480
pixels; the narrow dark ordered-conversation capture was visually inspected.

The maintainer's physical-scroll retest above is positive but retains a specific
insertion defect. Broader live-service, normal Wayland and Orca acceptance remain
open. These corrections do not establish a frame rate guarantee or eliminate the
remaining first-view construction costs.

## Four measured optimisation targets — 8 November 2026

The list-width/Pango, buffer/widget construction, CSS invalidation and Python
allocation targets now have focused implementations and regressions:

- Body labels request eight characters rather than one, avoiding the pathological
  narrow-layout measurement while preserving WORD_CHAR wrapping and selection.
- Avatars, media tiles and ordinary content/action parent chains are retained;
  initial avatars receive their identity during construction. Binding cancellation
  retires handlers, futures, metadata, selection and textures. Warning controls
  are lazy until content is hidden, and reconciliation snapshots native entries.
- Local action/menu-item CSS classes replace ancestor-based action matching.
- Unchanged context/Post DTOs are reused, and plain markup bypasses facet
  byte-copy/container work. GC and history-retention policies are unchanged.

**Final source and installed native suites each passed all 264 tests with zero
skips** under GNOME 51 X11/Cairo. Regressions cover actual cell recycling,
old/new CSS geometry, retained avatar/media parents and handler bounds, late
image rejection, disclosure, native selection, exact reading anchors and
Latin/CJK/Arabic/URL geometry at 11/16/24-point fonts and 320–800-pixel requests.
Lint, desktop metadata and schema checks passed. `./scripts/check.sh` still
fails to allocate a nested Flatpak instance; equivalent host-launched native
gates passed. Offline pinned build/export and local reinstall succeeded.

The final installed **full GUI smoke passed**, including normal/narrow profiles,
conversations, refresh Show/Undo, automatic paging, offline/draft recovery and
label controls. Installed high-contrast/16-point labels, conversations, refresh
and paging scenarios passed sequentially as well. An invented large-text label
capture was visually inspected. Captures remain in ignored build paths; tracked
screenshots were preserved.

The smoke investigation found an orchestration defect in both saved baseline and
candidate: refresh_staged checked an anchor, then capture resized the window and
invalidated that offset through text reflow. Refresh now establishes the final
800×820 geometry before capturing its anchor and waits for actual dimensions.
The position assertion remains intact, with useful numeric failure diagnostics.
This resolved the staged-refresh full-journey gap observed earlier in this report.
GDK timing/skipped-frame warnings remain visible and are not frame-rate proof.

[Performance evidence](PERFORMANCE.md) and [aggregates](performance-four-targets.json)
retain request probes (553.668 → 97.356 ms for 250 labels), final native rebinding
(717.272 → 536.702 ms per 1,000 bindings), and metadata allocation counts
(20,000 → 0 unchanged records). Compositor comparisons were rejected for missing
frames, changed work and tail regressions. Cold model-install latency remains
substantial; there is **no general FPS, whole-workload speed, physical-momentum,
Orca, ghosting, GPU-energy or live-service acceptance claim**. First-view buffering,
viewport scans and remaining dynamic structures are still documented future work.
No commit, upload, tag or release was performed.

## Reusable list cells — 8 November 2026

Feed/profile/search/conversation post rows now retain native core widgets across
GTK factory bindings, including header, selectable body label, action controls,
menu and controllers. One compact quote core is retained as well. Recycling
retires media and label gates, clears selection/popovers/delayed input/old model
references, resets conversation styling and binds callbacks to current data.
Avatars, media tiles, label/external-card structures and branch controls remain
item-specific; first-view native buffering is unchanged.

Source and final installed GNOME 51 X11/Cairo suites passed all **255 tests with
zero skips**. New regressions exercise actual native recycling over 250 posts,
100 successive action/data bindings, moderation/disclosure transitions, quoted
cell reuse and stale image completions. Pinned lint, desktop and schema checks
passed; `./scripts/check.sh` still cannot allocate a nested Flatpak instance, so
the native gate was launched through the host. Offline pinned build/export and
local reinstall succeeded.

The full installed X11/Cairo GUI journey completed conversation/label/profile
captures but timed out at `refresh_staged`, waiting for the staged-refresh notice.
The unchanged isolated installed refresh scenario then passed, including Show,
Undo and exact reading anchors. This is a full-journey validation limitation, not
a full GUI pass or an established attribution to the refactor. GDK frame-timing
warnings also occurred. The invented conversation capture was visually inspected;
tracked demo screenshots were restored and further captures use ignored build
outputs. Isolated installed conversation and refresh smokes passed under
X11/Cairo; the installed paging smoke also passed in the normal desktop renderer.
These functional passes do not replace the failed full-journey result.

The unmapped 1,000-binding benchmark built one body/action tree with reuse versus
1,000 with reconstruction (705.320 versus 1,681.110 ms total in one sample). This
simulates lifecycle work with current code; it is not an old-binary comparison.
[PERFORMANCE.md](PERFORMANCE.md) retains aggregate evidence and the actual
250-post scroll probes: the comparison was **rejected** for different travelled
distances/work and cold-tail regression. Cold p95 rose 33.858 → 43.049 ms; warm
maximum fell 112.447 → 80.489 ms. These mixed single-run results establish no
overall scrolling speed gain or frame-budget acceptance.

Physical momentum scrolling, normal Wayland visual quality, Orca and live-service
acceptance remain unverified. No renderer or host motion preference was changed;
no commit, upload or release was made.

## Scrolling review and targeted corrections — 8 November 2026

[SCROLLING_REVIEW.md](SCROLLING_REVIEW.md) records the current main-thread
architecture findings and remaining work. Automatic paging now starts two
viewports ahead and hides healthy Load more controls; errors, cursor stalls and
policy overrides remain actionable. Image failures and disabled automatic image
loading retain the reserved media height instead of collapsing the row.

Validation: pinned lint, desktop metadata and schema stages passed through
`./scripts/check.sh`; its nested Flatpak stage failed with `Unable to allocate
instance id`. The equivalent host-launched GNOME 51 source suite passed all
250 tests with zero skips under explicit X11/Cairo, including new early-paging,
healthy-footer and image-failure regressions. The offline pinned Builder
build/export and local reinstall succeeded. The installed invented-data paging
smoke passed sequentially after tests. It emitted a GDK frame-timing throttling
warning, so this is functional evidence only.

No new matched timing benchmark, physical momentum-scroll acceptance, Wayland
visual proof, live-service check or universal smoothness claim is made. Full
post-tree construction on bind, buffer-sized geometry scans and periodic
main-thread reading snapshots remain open. No commit or publication was made.

## Feed gap loading position — 5 November 2026

Load posts in between now captures the visible post and pixel offset before
replacing the focused gap button with its loading state, then restores through
the existing bounded, input-cancellable positioning path. Completion and failure
continue to capture the current position independently, so later scrolling wins.

The invented-data native regression reproduces the original jump from post 7 to
post 0 with the focused gap button; it fails without the fix and passes with it.
It verifies the post and offset through loading, failure, retry and insertion.
The focused test also passed against installed `/app/share/skyloom` code in the
GNOME 51 Flatpak under X11/Cairo. The offline pinned Builder build/export and
local reinstall succeeded. Lint, desktop validation and schema checks passed.

`./scripts/check.sh` could not launch its nested Flatpak runtime (`Unable to
allocate instance id`). The host-launched source keyboard suite ran 37 tests;
35 passed, including the new regression, while paging activation and native
pointer/keyboard focus tests failed. The complete suite and GUI smoke were not
rerun for this change. These results do not establish physical pointer/touch or
live-account acceptance.

## Renderer follow-up — 1 November 2026

Normal installed launch was checked with a fresh empty native window: Wayland,
Vulkan and no GSK_RENDERER/GDK_BACKEND override. Production launch does not force
Cairo. Matching X11/Vulkan and X11/GL top-jump probes pass with unchanged module
hashes, exact Undo and similar settlement to Cairo; no renderer speedup is
established for this workload. Both normal-backend Wayland GPU probe attempts
time out at the existing five-second settlement deadline and are excluded from
performance results. See [renderer evidence](PERFORMANCE.md#renderer-follow-up--1-november-2026). No production settings or app code changed.

## Adversarial thread-prefetch correctness/performance review — 1 November 2026

Three independent adversarial agents reviewed cache/request correctness,
performance and regression coverage. A second correctness review checked the
fixes and found the additional ancestry-only reuse defect before completion.
Confirmed findings were fixed:

- Cached descendants now merge under the original response anchor, retaining
  their unloaded reply continuations. An ancestry-only post is not treated as
  having fetched reply coverage; opening it requests its missing siblings.
- Cache reuse keeps the original fetch timestamp and does not insert duplicate
  descendant aliases. Freshness therefore expires after two minutes even with
  repeated opening. Local reaction revisions protect existing snapshots and
  older in-flight responses, while later acknowledged requests may accept newer
  server state. Pending reactions remain protected.
- Home fetches around the exact visible post instead of requesting a distant
  root that can omit deep replies. Root-based cooldown and shared request budgets
  remain. Foreground reads and mutations cancel speculative work; stale request
  slots recover, and sign-out clears snapshots/reaction state.
- Policy/worker notifications no longer restart viewport debounce. Mounted pills
  update only when their projected position changes; cache membership uses
  fetched-subtree sets. ReadingSession disconnect callbacks now retain distinct
  handler IDs, resolving the earlier teardown warning.

The final installed native gate passes **247 tests with zero skips** under
GNOME 51/X11/Cairo, including the adversarial cache, mutation, lifecycle and
foreground-preemption regressions. The installed Home/cache integration also
passes with warnings treated as errors (upstream DeprecationWarnings excluded).
The final installed conversation smoke passes at 800/480 pixels, including
branch retry/loading, ordering and selected-message return. Invented-data captures
are in ignored `build-prefetch-review/`; narrow dark conversation rendering was
visually inspected. GDK frame-timing warnings remain visible during smoke and
are not treated as frame-rate acceptance.

Stable/preview Ruff, formatting, SyntaxWarning compilation, shell syntax,
desktop entry and strict schema validation pass. The normal check wrapper was
invoked; nested Flatpak instance allocation remains an environment boundary,
so its native component ran through the documented host bridge without changing
assertions. The first source-suite attempt exposed an old cache fixture whose
request anchors were absent from its response; the fixture now uses valid
anchor/response pairs while preserving its budget/expiry/retention assertions.

The cached-dependency Flatpak rebuild/export and reinstall succeeded at
`46291aeadae2a0f797dd6a295a429cee4ab9e675f627f24b253f167d1432623b`.
The performance probe recorded matching source/installed hashes for all twelve
reviewed modules, before and after unchanged runs. A concurrent installed update
made an initial baseline unsuitable; the accepted comparison instead uses the
preserved original `e410e2ef` commit extracted into an ignored directory, without
reinstalling an older app. Compiled resource hashes match between the builds.

[Performance evidence](PERFORMANCE.md#thread-prefetch-adversarial-pass--1-november-2026)
and [retained aggregates](performance-thread-prefetch.json) show unchanged-pill
updates falling from 1,000 to zero, 200 policy notifications creating one timer
instead of 200, and 1,000 cache misses taking 4.339 ms versus 208.109 ms in these
samples. Six native long jumps per build go directly to zero and restore Undo
with zero pixel error. Destination-buffer hydration still takes roughly 0.4 s to
settle in the 250-post stress case; no faster-jump, FPS or hardware-energy claim
is made. Live-account prefetch effectiveness, physical scrolling/input, Orca and
real power/network transitions remain unverified. No real-account process was
inspected or restarted. The review itself did not publish or tag a release.

## Arrival notices at the top — 1 November 2026

Feed arrival notices now dismiss when the native vertical adjustment reaches the
top, including manual scrolling. This also clears the pending Go to top action
and feed unseen count, without invoking a jump or changing Undo. Arrivals already
at the top do not create a redundant notice. Staged Show actions remain available.

Stable/preview Ruff, formatting, compilation, desktop and schema checks passed.
The new native regression passed in GNOME 51 with X11/Cairo, including rejection
of the dismissed toast's stale action. The broader source runtime run reported
241 tests with 5 failures and 8 errors in conversation/prefetch coverage; this is
not a passing full-suite result. Three failing cases passed when run separately
against a temporary source copy excluding this change, so their cause remains
unresolved. The normal Flatpak manifest was subsequently rebuilt and installed
for manual review from `skyloom-origin`, backed by `flatpak-repo/`. Installed
commit `ae8df7b05c4ca7a37fcc0cf086956ecdb7552436d910d7750a79ca642e855813`
passes the new native arrival-notice regression against `/app/share/skyloom`.
Manual review of both installed apps was approved by the maintainer.
The exact staged commit snapshot also passes the arrival-notice regression and
existing toast/keyboard regression independently of the unrelated working tree.

## Thread prefetch and distant top jumps — 1 November 2026

Numeric position pills remain on Home and conversations without a `+` suffix;
incomplete context remains explained in tooltips/accessibility. Single-message
pills are suppressed. Home prefetches visible conversations after a 350 ms pause,
with one shared request slot, six requests per minute and a five-minute root
cooldown. A 32-snapshot cache supplies fresh context for two minutes. Foreground
requests take priority; automatic work obeys activity/network/cost/power gates,
and owned Home requests cancel on unmap/ineligibility. Replies never enter the
Home feed model. Conversations examine one viewport beyond visibility, using a
shared three-request lookahead budget for reply and ancestor continuations.

Top jumps longer than a viewport set the native adjustment directly to zero and
skip the top-edge bounce. A native 60-post fixture jumps from post 45, observes
no intermediate nonzero viewport positions, and verifies Undo restores the same
post and pixel offset. This is functional positioning proof, not a frame-rate
measurement or physical-input acceptance.

Validation:

- Stable/preview Ruff 0.17.3, formatting, SyntaxWarning compilation, shell syntax,
  desktop entry and strict settings-schema checks pass. `./scripts/check.sh`
  reached Flatpak but the nested environment could not allocate an instance;
  the equivalent native gate ran through `flatpak-spawn --host` with explicit
  X11/Cairo, preserving all assertions and rejecting unexpected skips.
- All 226 tests passed against source code in GNOME 51, then all 226 passed
  against the rebuilt installed code (zero skips). An additional installed-window
  integration test passed separately: visible Home prefetch enriches the pill
  without inserting feed rows, then opening the child reuses its cached snapshot
  without another service request. The current test inventory is 227.
- The cached-dependency Flatpak rebuild/export and local reinstall succeeded.
  Installed revision is `e410e2efae7810f2f04f33b3b88fa8e463045e93701dbcf221b37895c3d725d1`;
  all five changed application modules have identical source/installed SHA-256
  hashes. The distribution bundle was not regenerated.
- Installed `--demo --smoke-scenario conversation` passed at 800/480 pixels.
  Captures are in ignored `build-prefetch-smoke/`; narrow cards and expanded
  conversation pills were visually inspected. GDK frame-timing warnings remain
  visible; these captures do not establish smoothness under real workloads.

A warning-as-error diagnostic traced an existing fixture teardown warning to
`ReadingSession` signal-disconnection ownership in `reading.py`, outside the
prefetch code. The normal native suites pass with that warning visible; the
warning-strict diagnostic fails and is not counted as a pass. Live-account
prefetch effectiveness, physical scrolling smoothness, Orca and actual
network/power transitions remain unverified. The existing real-account process
was not restarted or inspected; restart Skyloom to use the installed changes.

## Ruff 0.17.3 review — 1 November 2026

Development Ruff is pinned to 0.17.3. Stable lint, selected preview checks,
formatting, SyntaxWarning-as-error compilation and shell syntax pass. The
`shared-clock-mock` preview gate now prevents process-wide clock patches in
refresh-monitor tests; test wall clocks are private while BOOTTIME constants
and real monotonic clocks are preserved. Clock isolation assertions extend
the existing deadline/resume cases. The regex compilation preview check had
no findings.

A source native suite using the available display and Cairo ran 221 tests:
219 passed, with failures in `test_label_controls_sync_mounted_copies_and_keep_keyboard_focus`
and `test_offscreen_pictures_release_textures_and_ignore_late_callbacks`. Both
modified clock test modules passed within that run. A forced X11 launch
crashed during GTK initialization. These runs do not replace earlier installed
application evidence or claim a clean full native gate. Other source edits
were occurring concurrently in this checkout. The two GUI failures passed
when run in isolation against both committed HEAD and the modified source. A
focused rerun of both changed clock cases plus those two GUI cases passed all
four tests. A separate six-test motion/monitor run had an unrelated animation
settling timeout. The full-suite timing instability remains unresolved.

## Position toast timing — 1 November 2026

Explicit top jumps now say “Moved to top”. Position Undo feedback lasts two
seconds rather than five and is dismissed on window deactivation, avoiding stale
top feedback when resuming further down a feed. The saved Undo action remains
available through the keyboard/menu; reaction feedback retains five seconds.
Native regressions cover timeout separation, inactivity dismissal and retained
Undo, alongside existing stable-position restoration.

`./scripts/check.sh` passed lint, formatting, compilation and metadata checks;
its nested Flatpak launch failed with “Unable to allocate instance id”. The
host-launched X11/Cairo native suite passed all **220 tests with zero skips**.
The installed invented-data refresh scenario passed (`GUI_SMOKE_SCENARIO_PASS: refresh`).
The offline Flatpak build/export and local reinstall succeeded. No live account
data was used; physical resume/touch and Orca acceptance remain unperformed.

## Initial private source repository — 1 November 2026

The maintainer authorised creation of
[`nedrichards/skyloom`](https://github.com/nedrichards/skyloom), verified private
through GitHub metadata. The host's previously empty Git directory was
initialised on `main` for the first source import. The reviewed snapshot includes
the latest shared thread pills, selectable-text click improvements, their tests
and current documentation. The 267-file audit excludes local data, credentials,
environments and build outputs; REPOSITORY_REVIEW.md records scope and findings.
The same application source passed 218 source and installed tests and the
installed conversation smoke in the preceding delivery. Publication-time static
checks pass; the nested runtime launch remains blocked as previously documented.
Private source hosting does not establish public-release or human acceptance.

## Shared thread context and forgiving card clicks — 1 November 2026

Position pills now belong to the shared PostRow, including feed, profile,
search and embedded quote cards. A bounded account-session index retains only
2,000 relationship/time/reply-count records and shares known context between
views. Discovering ancestors or replies updates mounted pills without rebuilding
post bodies or fetching extra threads. Independent conversations have separate
counts. Pills now require at least two known connected posts; isolated posts
never show `1/1` or `1/1+`, including when opened as a conversation. Counts describe known messages, not a guaranteed
server-wide total. Account replacement/sign-out resets the index.

Selectable body text now distinguishes pointer jitter from deliberate dragging
using GTK's desktop drag threshold. Existing selection and Shift state are
captured before the native label changes them. A sub-threshold mouse selection
can become an ordinary card click, while deliberate drags (including return to
the origin), word selection, Shift-click and touch selection remain native.
Opening still waits for the double-click interval and cancels on another click,
selection or unbind. Links retain their own activation.

Validation so far: all **218 source tests passed, zero skips**, in the supported
installed runtime under X11/Cairo. New coverage includes shared mounted
feed/search/quote pills, retained body identity, incomplete/complete context,
bounded eviction/cycles and jitter versus selection decisions. Static checks
passed through `check.sh`, which still cannot launch its nested Flatpak instance;
the host-launched suite completed instead. Signal-injected controller tests are
not physical pointer/touch or Orca acceptance. No live account data was inspected.

Final local delivery: offline Flatpak build/export/reinstall succeeded at commit
`540267572ac03c2877ca2ec83a4b99b3cf3d3f026d7b1aed827d370c08f60c07`.
All **218 installed-code tests passed, zero skips**, under X11/Cairo. The installed
normal-renderer conversation smoke passed at 800/480 pixels, including feed/quote
tiles and incremental conversation navigation. The narrow light feed/quote
capture was visually inspected; captures stay under ignored
`build-shared-context-review/` and contain invented records only. All 42 installed
modules and compiled resources match the source/build. Existing GI cleanup and
GDK frame-timing warnings remain. Physical input feel, large text and Orca remain
human acceptance checks; no running account process was restarted. The refreshed
local bundle SHA-256 is
`67de7efb6b4c3164289003d7f5624cec7f82377f09a879ecfc81b9c9e23c3a61`.

## Conversation position pills — 1 November 2026

Each conversation post now has a small theme-coloured pill beside its timestamp,
showing its position among loaded posts in reading order (for example `1/6`).
Incomplete context adds `+`; the tooltip and accessible label explain the loaded
scope. Missing posts, loaders and embedded quotes are excluded. Mounted pills
update without rebuilding post content when earlier messages or replies arrive.
This is a local reading position, not a guaranteed total for server-omitted replies.

Validation: `./scripts/check.sh` passed Ruff, formatting, Python compilation,
shell syntax, desktop-entry and schema checks, then stopped before native tests
with Flatpak's `Unable to allocate instance id`. The documented host bridge also
failed with `Could not connect: Operation not permitted`. All 11 standalone
conversation-model tests passed. A native regression was added for partial counts,
ancestor insertion, completed counts and retained row identity, but could not be
executed here. Installed build/export/install, GUI smoke, narrow/large-text visual
review and screen-reader acceptance remain unverified for this change. No host
installation or running account was changed.

Follow-up local installation: the host bridge became available. The offline
Flatpak build/export and user reinstall succeeded at commit
`ff9639b3c42f5b0d6c0bb956d83efb054e926b1435456cd6882cdd28f878f9fd`.
All **211 tests passed, zero skips**, against the installed application under
explicit X11/Cairo, including the new pill regression. The normal-renderer
installed conversation smoke passed at 800/480 pixels; the narrow dark capture
was visually inspected and shows the pills beside timestamps. Captures contain
invented records only and remain in ignored `build-thread-position-review/`.
Installed changed modules and compiled resources match the source/build hashes.
The local bundle was refreshed with SHA-256
`362a49c88438971fff800d34df2b1ba98e36b4ecc57f474a29c62e977af98d97`.
The direct `check.sh` retry still stopped at its nested Flatpak launch (NETLINK
socket/ldconfig sandbox error) after static checks passed; the host-launched
installed suite above is the completed runtime gate. Existing GI cleanup and
GDK frame-timing warnings were observed. Large-text/Orca/live-service acceptance
remains manual; no running account process was restarted.

## Animated responsive sidebar — 28 October 2026

The reported abrupt disappearance was the responsive resize handoff, rather
than the existing animated toggle. Libadwaita's default collapse path explicitly
sets sidebar visibility without animation, and BreakpointBin temporarily unmaps
its child while applying the layout. Starting an animation during that unmap
also skips to the endpoint. Both contracts were checked against upstream 1.10.0
source and the supported installed runtime.

`Navigation` now retains control of visibility with `pin-sidebar`, waits for map
when necessary and uses the native spring after the layout handoff. Content and
models remain mounted, only the latest pending target is kept, and native focus,
accessible toggles, menus and gestures remain in charge. Reduced motion retains
the instant breakpoint behaviour through a local settings watcher; the legacy
disabled-animation setting remains native. No custom global animation setting,
custom animation loop, copied upstream code or account-data inspection is involved.

Four native regressions cover actual breakpoint/frame geometry and focus return,
reversing a transition, modern/legacy motion suppression and a 250-post native
feed resize. The dense-feed probe reproduced zero intermediate sidebar frames
on the preceding installed build and ten on the final candidate in separate runs.
Its initial narrow reflow still took hundreds of milliseconds; the bounded
three-frame handoff starts the spring after that reflow instead of letting it
consume the animation clock. These samples establish a visible transition, not
a general resize/frame-rate guarantee.

Validation: lint, formatting, compilation, shell syntax, desktop entry and schema
checks passed. The final focused source run passed all 12 navigation/dense-window
checks under X11/Cairo. The required full source `check.sh` was run: its final
210-test run hit intermittent logical loader-selection and profile-focus failures
in standalone ConversationView fixtures, which do not instantiate Navigation.
Earlier complete source/installed runs passed 210 tests; a failed loader-focus
case also passed on its own. No failing assertion was suppressed or changed.
Full-suite focus stability remains a limitation, separate from the sidebar
regressions. Normal-session full suites additionally hit existing feed frame-wait
timeouts with both default and Cairo renderers; explicit Flatpak X11 flags are
documented in DEVELOPMENT.md.

The rapid resize-reversal test emits a native AdwGizmo snapshot-allocation
warning, despite passing final-state/content checks. This and the standalone
focus-test instability remain in ROADMAP.md. Existing GI cleanup/deprecation and
GDK frame-timing warnings were also observed. No physical-input or human account
acceptance is claimed, and no running account window was restarted.

Final installed evidence: the offline Flatpak build/export/reinstall passed, and
the installed application's own code passed all **210 tests, zero skips**, under
explicit X11/Cairo. The final normal-renderer installed navigation smoke passed
at 1280/480 pixels, including actual sidebar buttons, single-menu ownership, F6,
Back and preserved feed data. Its narrow dark endpoint was visually inspected.
All 41 installed Python modules and compiled resources match the workspace/build.
Current package commit and local bundle checksum are in BUILD_ENVIRONMENT.json.
The smoke captures and probes stayed under ignored `build-sidebar-review/`;
they contain invented records only. No account process was restarted, and no
release, repository upload or tag was created.

## Repeated update notices — 28 October 2026

The update-notice controller reset its announced flag whenever a page/window was
hidden, inactive or covered by a menu/dialog. Returning could therefore replay an
existing pending batch. Feed refresh also re-offered accumulated unseen posts
even when the refresh added nothing. These are reproduced implementation paths;
no personal feed, account logs or session were inspected to establish which path
produced the reported three notices.

Notice lifetime now survives visibility/activity interruptions. Batch identity
deduplicates repeated offers without losing the latest callback or the persistent
menu/keyboard action; new identities can announce with an unchanged count.
Notification batch identity is insensitive to ordering, and feed notices require
additional arrivals. Native regressions cover repeated offers/dismissal,
visibility interruptions, deferred first presentation, equal-count new batches,
latest/stale callbacks and quiet metadata-only feed refresh.

Validation: the host-side `scripts/check.sh` passed lint, desktop/schema checks
and all 206 native tests with zero skips. The rebuilt/reinstalled sandboxed app
also passed all 206 tests using its own installed code, and its named refresh GUI
smoke passed stable insertion, Go to top/Undo, cost/power/backoff and manual
refresh checks. All 41 installed Python modules and compiled resources match the
checkout. The offline Builder/export/install and local bundle export passed;
current commit/hash evidence is in `BUILD_ENVIRONMENT.json`. Captures stayed in
ignored `build-sharing-smoke/`, with invented records only.

An earlier source run hit the existing keyboard restore test's frame-wait timeout;
the complete host check and installed suite subsequently passed it without
changing that test or its assertions. The nested direct check also initially
caught test formatting, corrected before the passing gate. Human/live-account
reproduction is not claimed; no running account window was restarted. Earlier
full GUI/high-contrast and performance sections retain their original scope.

## Source sharing review — 28 October 2026

[REPOSITORY_REVIEW.md](REPOSITORY_REVIEW.md) records the pre-upload file audit,
strengthened ignore rules, explicit GPLv3-or-later grant/package metadata and
welcoming personal-project contribution policy. No apparent credentials or
personal home paths were found in prospective upload files; invented-data PNGs
were reviewed. No usable Git metadata was available locally or on the host, so
staged files and prior commits remain unverified. No GitHub repository was
created or uploaded.

For this documentation/metadata change, lint and desktop/schema checks passed;
the direct host-side source suite passed 204 tests with no skips using installed
Flatpak dependencies. The combined script's nested Flatpak launch failed; later
host-wrapper and demo-smoke attempts were blocked by desktop-bus permissions.
No new GUI acceptance, rebuild, bundle or installation is claimed. Application
code is unchanged; the prior delivery evidence below retains its original scope.

Skyloom 0.1.0 is a local development preview for GNOME 51/x86_64, maintained by Nick Richards. The initial implementation plan has been retired. [FEATURES.md](FEATURES.md) is the implemented scope, [ARCHITECTURE.md](ARCHITECTURE.md) explains the actual code and storage, and [ROADMAP.md](ROADMAP.md) contains remaining release gates and optional features.

## Adversarial review resolution

All thirteen findings, including the reported Appearance chooser seam, are implemented. [CODE_QUALITY_REVIEW.md](CODE_QUALITY_REVIEW.md#resolution) maps each original finding to its fix and regression coverage. Storage epochs and cancellation-safe secure IO prevent stale operations crossing account ownership; shared request scopes, row reconciliation, Undo tokens and input epochs remove competing completion/positioning paths. People/notification cursor bookkeeping and refresh eligibility now have shared owners. Legacy payload migration preserves fresher records.

Position-only checkpoints of a 250-post window now serialize only the bookmark, with zero post serialization and one changed SQLite row (previously 251 serializations and 501 changed rows). Cached-post lookup uses its URI/recency index. Decoded images have both byte/count budgets and viewport consumer release, with stale-result and completed-future cleanup. Strict native and performance gates reject missing runtime coverage, unexpected skips and missing/insufficient timing samples.

Final functional, visual and measurement evidence is recorded below and in [BUILD_ENVIRONMENT.json](BUILD_ENVIRONMENT.json). Historical performance measurements retain their original build scopes. The current 30-post run measures 58.24/57.49 fps, but a clean relative timing comparison remains blocked by insufficient baseline feedback and differing scroll workloads; the comparator rejects it. No account data or credentials were inspected and nothing was published.

## Completed implementation

Feed arrivals are available immediately above the reader. Live refresh preserves existing order and visible identity/offset; restart accepts the first fresh head order unless intervening input takes control, and explicit manual refresh accepts server order and goes to the top. The feed toast navigates with Go to top. Undo returns to the reading place without removing arrivals or reverting reactions/cursors. Disjoint cached history stays readable behind real-cursor gap paging with native retry.

Indexed SQLite retains every fetched feed page/quote with targets of 10,000 posts per feed and 50,000 per account. Count/30-day cleanup is automatic, with protected saved windows and bounded sweep slack. Twelve reading windows retain up to 250 posts independently of the archive. One-second coalesced worker checkpoints save URI/offset/selection/neighbours. Pre-navigation/feed-switch/close capture saves geometry before unmap; shutdown cleanup saves final positions. Legacy caches stay readable; offline page replay requires complete records. Account epochs checked under the storage IO lock reject stale work, including a filesystem thread that outlives coroutine cancellation. Archive cleanup never deletes drafts.

The header New post control uses the normal native plus button style. The composer Post control retains its suggested-action styling; icons, shortcuts, activation and native hover/focus behaviour remain unchanged.

The full-width new-item banner is replaced by a page-scoped native toast in the shared overlay queue. It does not resize/reposition the list; dismissal preserves navigation, available through Show new items in the menu and Ctrl+Shift+Home. Hidden pages/dialogs/popovers defer their notice. Brooklet-style upper-edge feedback adds a bounded 360 ms damped snapshot peek for wheel/no-op keyboard/top navigation, while smooth/touch overscroll stays native. It respects both motion preferences, inactivity and power saver, with no model/adjustment mutation or persistent animation tick.

Post cards now separate reading, identity, labels and actions more clearly. The avatar/name/handle form one compact profile target; unused header space opens the conversation. Label chips wrap at natural widths without grid-cell focus stops. Caption metadata and consistent symbolic icon/count actions leave the body prominent. Pointer selection keeps the logical command cursor without a full-row highlight; direct keyboard row focus outlines the clamped content, while child controls retain their own focus rings. Stable profile focus keys survive conversation content rebuilds. Original outline/filled symbolic hearts are bundled because the requested runtime heart icon was unavailable.

A full performance pass now has a reproducible installed-app runner and [measured report](PERFORMANCE.md). It covers frame/presentation pacing, CPU, memory, row binding, media, refresh/Undo, conversations, profiles, search, native transitions and reduced motion using invented data. It delivered shared immutable textures and coalesced/cancellable image work, viewport-aware loading, lazy post menus, recycled wrappers/native separators and key-indexed counter updates. The 60 fps target is not met in every dense/cold-view case; the report and roadmap preserve those results rather than claiming unconditional smoothness. A supplemental interaction pass also removed 100 notification-row rebuilds from Mark seen; a follow-up adds fixed-size accessible unread markers and measures a 17.3 ms main-thread completion. The older static presentation gaps include asynchronous waits and do not establish blocked rendering. Refresh now uses one eligible deadline instead of minute polling; inactive paging/media defer work, and brief visible reaction/read feedback respects power saver and both motion preferences. No production renderer or system animation/power preference was overridden.

Feed reconciliation preserves loaded history/cursors, reuses unchanged PostObjects and updates counters on existing controls. One arrival inserts one model item; ten counter refreshes retain the same body/media widgets with no additional image jobs in native fixtures. Manual-refresh visible arrivals get a layout-stable 160 ms opacity reveal after top positioning settles, with reduced-motion and input/unmap cleanup. Undo restores reading position while retaining the current data/cursor. At the history bound, refresh rewinds to real page cursors; a disjoint head keeps readable history with an explicit gap. This is allocation/request evidence, not a measured speed comparison with Brooklet.

Native account/session, Following/pinned feeds, conversations, reactions, composer/drafts/images, profiles/follow/moderation, search, notifications, preferences, menus, responsive navigation, system appearance, keyboard/list affordances, automatic paging and connection/power/suspend-aware refresh are wired through the SDK and shared native models/widgets. Unsupported reporting/video use explicit external routes. The identity is `com.nedrichards.Skyloom`, with original refined Open Loom icons and Nick Richards credits.

The closing plan audit corrected draft discovery after cleared drafts, cached post/quote reopening, offline new/reply/quote drafting, cache-first feed switching and server-error/offline classification. It added bounded account-private image persistence (128 MiB / 2,048 files), restart/offline decoding, eviction, corrupt-entry recovery and sign-out invalidation of in-flight writes. Account controls follow live connectivity; Mark seen updates visible notifications after success and obtains the actual unread count. F6 also works on pages without a feed list.

Preferences now uses concise Reading, Updates, Storage and Authentication groups. Sign out moved out of the overflow menu to the final Authentication group, using a native destructive row and confirmation. Cancel returns to Preferences; failures retain a retry route in the dialog.

Overflow menus now follow sidebar visibility exclusively: only the sidebar or current page menu is visible, including after repeated hide/show, resizing and opening nested pages. F10 targets the visible menu, and hiding its button closes an open popover. Two native regressions and the installed fixture smoke cover these transitions.

Search now fills the available height with a readable initial prompt, spinner, no-results or error/retry state. It retains one scroller with fields/results, releases the full-height header when results arrive, and cancels stale requests when the query is cleared. Native regressions cover resizing, state readability, retry and returning to results; fixture captures show actual Search pages rather than the formerly mislabelled Home capture.

Startup now follows the verified Agile Rates pattern: neutral pending content, a 200 ms delayed loading indicator and native 150 ms crossfades. The login form stays hidden until a missing session is confirmed; saved sessions enter the shell, and lookup errors offer separate recovery. Seven native startup regressions cover real rendering with synthetic async outcomes, cancellation and animation preferences without accessing an account keyring.

Content labels now use wrapping icon chips with readable names, post/author/profile scope and lazily built native explanation popovers. Exact values remain selectable/copyable; custom labels are not assigned invented meanings. Three inline labels plus an all-labels count keep crowded posts compact. A soft hidden-content card, clear Show action and native reduced-motion-aware reveal replace the old expander. Visibility choices synchronize mounted copies without changing the default to show content.

The bootstrap prompt, one-shot agent runner and speculative duplicate product/design/architecture/quality/release plans have been removed. Maintenance instructions, implemented features, architecture, development/testing commands and a single future roadmap replace them. No public repository or release was created.

## Current evidence

The header-button styling change passes `check.sh` (157 tests). Its installed fixture verifies the normal plus button, tooltip, click-to-compose, and the composer Post button's primary styling with a valid invented draft; no post is published. Updated header/composer captures and exact build/hash are recorded with the environment evidence. Earlier header/overlay acceptance scopes remain below; current full-app evidence is recorded separately.

Profile actions/browser/filter now share one natural wrapping row. The account card is the Profile destination in a fixed sidebar footer; the duplicate Profile row is removed. Installed fixture checks measure browser/filter alignment, footer placement, repeat activation and narrow-window pane focus, with normal and high-contrast/large-text captures. No account/session data is changed.

The background-refresh investigation found a local amplification path: `sync_offline` called `show_offline`, which emitted whole-list replacement notifications for every mounted view even when connectivity was unchanged. Row reconstruction resubmitted media, while avatar jobs were not included in row cancellation. The worker caps outstanding jobs at 32 and generated its own “Too many requests” error; this differs from the existing server-429 cooldown. The fix updates reaction sensitivity in place, skips unchanged connection/loading-policy work, cancels recycled avatars, rechecks queued cache hits and preserves feed-picker identity during metadata replacement. No account traffic or private logs were inspected, so this is a reproduced code-path diagnosis, not a claim about the exact server response in the user’s session.

Conversation navigation reuses the currently visible anchor URI and pending request; repeated activation focuses its visible body without pushing another page. Different posts retain distinct Back steps. A native regression exercises rapid activation before loading, A/B navigation, Back and reopening from the feed; the installed fixture smoke checks repeated activation after rendering. The current native suites retain this regression; the earlier navigation-fix full smoke passed after a Search resize timeout on its first run.

Conversation ordering is now implemented in the graph/projection model and a dedicated native ConversationView. Siblings read oldest first, parents precede children, and subtrees remain together; loaded depth survives refresh. Connected rails, parent links, opened-message state, missing-message rows and local load/retry controls share the existing scroller/cursor. Alt+Up/Down and header controls navigate loaded relationships; Return has Undo. Feed comments, including cross-author replies, open their exact URI in this view. Verified adjacent same-author feed previews are joined without reordering the feed. Current validation is recorded below; Orca/physical input/live-service completeness are not claimed.

Preferences fixture checks also exercise each settings binding, wide/narrow layout, the reachable bottom authentication action, native confirmation, cancellation/focus return and a synthetic sign-out failure with retry enabled. No real account was signed out.

Final build/test values and bundle hashes are recorded in [BUILD_ENVIRONMENT.json](BUILD_ENVIRONMENT.json). The delivered build’s source `check.sh` run passed all 204 tests with the default renderer under X11; the installed functional suite passes all 204 with Cairo under X11. The product renderer preference is unchanged. All 41 final modules and the CSS resource match the checkout. The installed fixture smoke checks the actual Go to top notification, immediate insertion and stable order/anchor/object/cursor/position Undo/backoff behaviour, and the translated peek/rest snapshots. The Appearance chooser has current light/dark, wide/narrow and high-contrast/16-point captures, including its native popover. No real-account process was restarted or inspected.

Controller fixtures now explicitly supply window activity and establish native logical list focus. The demo smoke also supplies activity eligibility; inactive paging/peek contracts are tested separately. Earlier uncontrolled-activity runs had no-peek/scroll/frame failures, and earlier default-renderer/composer timeouts remain recorded limitations. A native toast ahead of Show in the synthetic connection-policy sequence also hid that control during an early smoke attempt; the fixture now clears those unrelated notifications after checking policy gates, then waits for the actual Show toast. No production toast-queue policy is overridden. The isolated two-page paging fixture starts empty because refresh now retains disjoint history. Refresh assertions require the same post and exact pixels when reachable, with a directional clamp only at the native scroll boundary after reflow. Native regressions independently assert exact padded-card fragment offsets and pre-navigation checkpoints. These fixture checks do not establish physical activation, injected keyboard/touch delivery or Orca acceptance.

| Check | Evidence |
| --- | --- |
| Lint | PASS: all first-party Python files; pinned Ruff stable and selected preview rules, all Python formatting, SyntaxWarning-as-error compilation and shell syntax. |
| Native integration | PASS: 204 source tests with the default renderer and 204 final installed functional tests with Cairo, no skips, in GNOME 51 with installed dependencies/decoder sandbox; domain, auth/refresh, serialization, errors, bounded caching, worker dispatch and GTK/controller contracts. |
| Source GUI | Earlier full native fixture smoke, including notification read/connectivity controls, cached feed switching, online server-error recovery and offline saved-post/reply-draft save/reopen/no-publish/F6. |
| Installed Flatpak | PASS: clean offline build/export/install and 204 installed-module functional tests with Cairo; default-renderer timing limitations below; current immediate-insertion/Go to top/position Undo and full standard fixture smoke; current preferences high-contrast/16-point captures and earlier profile/card captures remain available. Bundle hashes and exact current scope are in the environment record. |
| Metadata | Desktop entry and strict GSettings schema validation pass. AppStream composition/export succeeds; strict AppStream validation still exits 3 for the missing public homepage. |
| Privacy | Manifest grants network, display/IPC/GPU and only Secret Service bus access; no broad home access. Prior dummy-keyring test used a separate invalid synthetic entry and deleted it. No real session was inspected. |
| Earlier service reachability | Public unauthenticated describeServer over TLS was checked during initial implementation; no authenticated interoperability claim. |

Conversation regressions cover ordering across reversed siblings, UTC offsets and invalid dates; causal subtrees; gap/frontier placement; incremental sibling/ancestor insertion; shallow refresh retaining deeper messages and local reactions; shared visual/keyboard indices; cross-author comment activation; joined previews; Return/Undo; cached-parent presentation updates; reaction-control focus restoration; logical loading focus and completion isolation from other content views. Earlier native attempts hit frame deadlines on this compositor; final native checks select X11 explicitly and retain all assertions. Busy controls retain logical loader focus, failed loads restore their retry control, and completion in another content view cannot take the current page’s focus. The fallback retry repeats the failed operation rather than an unrelated branch. Installed GUI sessions run sequentially.

Native keyboard regressions now wait for rendered frames and pending position callbacks, bounded by two seconds, instead of assuming 150 milliseconds is enough on a loaded compositor. They still assert actual scroll position, compact identity and Undo results. GUI runs remain sequential to avoid occluding the windows under test.

## Visual evidence and limits

The new image experiment reduces tracked native references/estimated decoded residency from 64/192 MiB to 12/48 MiB, using a simulation of prior retention and separate processes. Whole-process peak RSS is essentially unchanged. [PERFORMANCE.md](PERFORMANCE.md#adversarial-refactor-measurements--28-october) preserves its scope and limits alongside current scrolling results.

Earlier installed Wayland performance runs cover full 30-/250-post sequences, 480-/1100-pixel windows, reduced motion, a plain native-list control, OpenGL comparison and three startup-only trials. Normal-sized continuous scrolling measured near 59–60 fps; dense views remain around 34–37 fps with roughly 0.6-second cold-view spans. All-post counter update time fell from 90.9 to 14.0 ms and sampled stress peak RSS from 434.3 to 384.2 MiB. These are sampled fixture results, not a claim of 60 fps in every case, live-service throughput or physical-input proof. [PERFORMANCE.md](PERFORMANCE.md) keeps full scope, percentiles and follow-up work visible.

[Fixture screenshots](../screenshots/demo/home-1280-light.png) cover 480, 800 and 1280 logical pixels, light/dark appearance, full/compact profiles, conversations, described images, labels, menus, concise Preferences at 800/480 pixels and bottom authentication controls, notification read state, refresh and offline pages. Conversation-specific high-contrast/16-point captures and earlier full-app captures are in `screenshots/high-contrast-large-text/`. Label popovers have separate `labelled-*-popover.png` captures because GTK renders them on a separate native surface. Chip and hidden-card borders use Adwaita’s contrast-aware colour. Startup-specific large-text/high-contrast validation also uses rendered fixture tests. Current refresh captures show both the [new-post overlay notification](../screenshots/demo/new-posts-800-light.png) and [latest posts shown](../screenshots/demo/new-posts-shown-800-light.png), with matching high-contrast/large-text captures. These are rendered native widget captures using invented accounts, not real-account or whole-desktop captures. Final selected icon renders are in `design/icon-concepts/`.

Live-account sign-in/restore/publication/mutations, Orca, physical touch/file portal, actual network/power/suspend transitions and 1600-pixel layout acceptance remain human/environment gates. Current Xwayland synthetic keyboard reruns receive no key events at the window capture handler. The card pass initially stopped at J, but diagnostic capture confirmed zero Down/J events, focus still in the header and selection already at zero before injection; that initial selection was not evidence of a delivered Down. An earlier revision passed physical input, but current physical-input success is not claimed. Controller/focus/widget tests are a different layer and are not substituted for that claim. This desktop is 1503 logical pixels wide.

Known upstream GI asyncio-policy and HTTPX upload deprecations remain visible. Prepared upload copies are retained until sign-out, including abandoned copies. The archive does not include every profile/conversation/notification. Reactions in loaded feed windows join coalesced checkpoints; records never fetched remain unavailable offline. A forced process termination can lose the last unsaved second of position changes. English is delivered; there are no translation catalogues. No hosted CI/static typing/ShellCheck execution is claimed. See the roadmap for these follow-ups.

The existing real-account process was not restarted, inspected or removed. Restart Skyloom to use the installed update. [DEVELOPMENT.md](DEVELOPMENT.md) and [TESTING.md](TESTING.md) give reproducible commands; installed checks and real-account acceptance are clearly separate.


## Single-message position suppression — 1 November 2026

ThreadContext suppresses pills until two connected posts are known, including
explicitly opened single-post conversations and reply-count-only evidence. The
six focused regressions pass. The initially unavailable Ruff 0.17.3 tool is now
available; the later validation below supersedes the earlier tool-version block.

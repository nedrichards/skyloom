# Performance

Skyloom targets a 16.67 ms frame budget on a 60 Hz display. That is a target, not an unconditional guarantee: the measurements below include missed frames and cold-view construction stalls. Keep tail latency visible when reviewing changes.

## Thread prefetch adversarial pass — 1 November 2026

[Thread prefetch measurements](performance-thread-prefetch.json) retain the exact
module/probe hashes, unchanged-source checks, deterministic work counts and native
samples. Three independent adversarial reviewers examined request ownership,
cache correctness, test gaps and performance. The baseline code was extracted
from immutable Flatpak commit `e410e2ef` into an ignored directory, rather than
using a moving installed application. The final installed candidate is
`46291aea`; both use the same compiled resource hash, GNOME 51 and explicit
X11/Cairo. No real account was inspected or used.

| Work | Original feature | Reviewed candidate |
| --- | ---: | ---: |
| Unchanged mounted-pill updates for one unrelated 250-post prefetch | 1,000 | 0 |
| Debounce timer adds/removals for 200 unchanged policy notifications | 200 / 199 | 1 / 0 |
| 1,000 misses across a full 32 × 250-post snapshot cache, wall time | 208.109 ms | 4.339 ms |
| Median native top-jump action, six samples | 78.396 ms | 79.931 ms |
| Median top-jump settlement, including polling/layout | 407.885 ms | 421.966 ms |

The first two reductions are deterministic work counts, not timing claims. Cache
membership uses a set of actually fetched subtree URIs, replacing nested scans;
ancestors present only for context cannot stand in for a reply fetch. Snapshot
reaction reconciliation is bounded and versioned, so local mutations survive
older responses without pinning acknowledged state over newer server requests.
Foreground reads/mutations cancel speculative work instead of waiting behind its
serialised service request.

Both native runs used 250 text posts, an 800-pixel window and alternating positions
45/249 repeated three times. All adjustment samples went directly to zero, all
Undo anchors matched with zero pixel error, and native row binding ranged from
zero to 46 in both runs. Destination buffer construction remains expensive: these
samples do **not** establish a faster jump, universal 60 fps or eliminated
stuttering. Settlement is three stable checks on a 10 ms poll, not a compositor
presentation measurement. The shared desktop and six samples do not support
attributing the small timing difference to a regression or improvement.

Normal feed/prefetch paths already batch relationship additions. The deliberately
adverse microbenchmark that changes 200 individual records in a full context
still costs about 1.2 seconds cumulatively; it is not the normal prefetch workload
and does not justify a speculative graph rewrite. A single bulk addition is
reported separately in the retained JSON.

Reproduce with `scripts/benchmark-thread-prefetch.py --native --output OUTPUT`
inside the installed runtime, selecting immutable baseline/candidate code through
Flatpak's explicit `--env=PYTHONPATH=...`. Run native measurements sequentially,
separately from tests/smokes, with identical arguments. The probe records module
hashes before and after and rejects source changes during a run; raw captures
belong in ignored `build*/` directories.

## Renderer follow-up — 1 November 2026

A fresh empty window in the normal installed sandbox, with no backend/renderer
options, reports `GDK_BACKEND=None`, `GSK_RENDERER=None`, `GdkWaylandDisplay` and
`GskVulkanRenderer`. Skyloom's launcher, desktop entry and manifest do not force
Cairo. The explicit Cairo/X11 arguments belong to functional tests and the
preceding matched probe; they do not persist into normal launches.

The same native top-jump workload was also measured with Vulkan and OpenGL on
X11, keeping the installed module hashes identical. The Cairo row below reuses
the preceding candidate sample. Each sample has six jumps in a 250-post list;
these are single sequential runs, not confidence intervals.

| Actual renderer | Median action | Median settlement |
| --- | ---: | ---: |
| Cairo | 79.931 ms | 421.966 ms |
| Vulkan | 80.091 ms | 412.860 ms |
| OpenGL | 85.358 ms | 421.240 ms |

All restore the same Undo key with zero pixel error and bind at most46 destination
rows. There is no clear improvement for this particular jump from changing the
renderer. These measurements do not compare continuous scrolling, image upload,
GPU presentation or power consumption. General GPU drawing benefits cannot be
quantified from this workload.

Fresh Wayland/Vulkan and Wayland/GL top-jump attempts both fail the existing
five-second settlement deadline; incomplete attempts are excluded from timings,
not counted as passes. The X11 figures therefore cannot establish normal Wayland
performance. Vulkan/X11 emits nonfatal swapchain-suboptimal warnings.
[Retained evidence](performance-thread-prefetch.json) includes renderer types,
module hashes, all samples, the default-launch check and failed attempt status.

## Reproduce

Run `scripts/performance-pass.py` inside the installed Flatpak, exposing this checkout. The runner starts its own demo application with memory preferences and a temporary invented-data store. It never restores an account, reads an account database or makes a network request. Run it separately from tests and other GUI sessions, with the fixture window unobstructed.

```sh
flatpak run --user --command=python3 --env=PYTHONPATH=/app/share/skyloom \
  --filesystem="$PWD" com.nedrichards.Skyloom \
  "$PWD/scripts/performance-pass.py" --output "$PWD/build-runtime/performance.json"
```

The default is a 250-post stress case. Repeat with `--posts 30` for a normal API-page-sized case, `--width 480 --posts 30` for a narrow window, and `--reduced-motion` for the stress case without nonessential motion. `--scroll-only` limits a content run to initial/forward/reverse scrolling and idle for renderer comparisons. `--startup-only` measures the initial demo window. `--control` runs a shorter plain-label list to establish a native scrolling reference; it is not an application performance score. `--profile` produces a separate Python `.pstats` capture: its overhead makes that run unsuitable for frame comparisons. Keep captures under ignored `build*/` directories.

Use `--idle-only` for separate eight-second quiet and unmapped samples. Context switches and process CPU are diagnostic proxies, not hardware wakeup or energy measurements; the unmapped phase includes the hide transition.

Use `--interactions-only --posts 30` for the supplemental editing/notification/menu/connectivity run. It includes a real demo reaction roundtrip, a 300-character draft with asynchronous autosave, four local image previews, 100 notifications and Mark seen, Preferences, an image dialog, post menus and offline/online control sensitivity. It does not publish or touch an account.

The scenarios exercise real post/media/quote/label widgets, shared worker and decoder, list construction and forward/reverse scrolling, all-post counter updates, Show/Undo, label preferences, a branching conversation, Back, unified profiles, search, sidebar transitions and idle. The scripted scroll writes the real native adjustment at frame-clock ticks, at 1,800 logical pixels/second; it is not proof of physical mouse/touch delivery. The runner rejects a scrolling phase with no movement. Dense snapshots are capped at the supported 250 posts and use actual page boundaries for refresh/Undo.

Images come from the shipped SVG/PNG fixtures. Decode and filesystem work are real; network latency and the diversity of real-world photographs are not represented. Initial demo media may already be cached for the first forward sweep. The counter phase deliberately updates every loaded post together, exceeding the usual single-reaction workload.

## Measurement scope

The `first_frame_ms` timer starts immediately before `application.run()`, excluding imports/application construction. `process_first_frame_ms` uses this Python process’s `/proc` start tick and CLOCK_BOOTTIME, including those costs to kernel tick precision, but excludes the earlier Flatpak launcher; startup-only runs record it separately.

The runner records each phase's action duration, main-thread worker-completion duration, process context switches, process CPU time, frame-clock before-paint/after-paint span, callback intervals, actual presentation intervals when the backend supplies them, peak process RSS, row binds/unbinds, image calls and retained rows/jobs. CPU time includes worker/renderer threads; peak RSS is cumulative within a process and includes GTK/renderer caches. A bound row is not necessarily visible: GTK maintains a substantial prefetch buffer.

[GDK presentation timestamps](https://docs.gtk.org/gdk4/method.FrameTimings.get_presentation_time.html) indicate when a frame became visible. They are [filled incrementally and can remain unavailable](https://docs.gtk.org/gdk4/method.FrameTimings.get_complete.html). A before-paint/after-paint span is not a GPU completion timestamp. Frame gaps while a static page is not drawing are not dropped frames. Evaluate presentation cadence only during continuous scrolling/animation. Exact `>16.67 ms` counts include refresh-clock rounding/jitter; the `>25 ms`/`>50 ms` counts and tail percentiles make clear missed intervals easier to assess. Do not turn static-page gaps or missing samples into an invented FPS value.

The Python hotspot capture identified row construction/binding, model replacement, eager menu construction and repeated model scans. A plain native-list control separates basic toolkit/display cadence from the cost of the complete post tree. This pass does not claim kernel/GPU stack sampling or live-service profiling.

## Changes

- Cache one immutable texture per decoded image and share it among pictures, avatars and previews. Texture construction stays with worker decoding, using the existing sandboxed decoder and size restrictions. GTK documents [immutable textures and their threading contract](https://docs.gtk.org/gtk4/section-threading.html); no widgets move off the main thread.
- Coalesce simultaneous identical image requests. Cancelling one consumer keeps other consumers working; cancelling the last stops shared work. Account generations isolate in-flight results and prevent stale cache insertion.
- Queue uncached media until its widget is near the viewport, with half a viewport of preload above/below. Cached textures can be assigned immediately. Recycling/closing cancels queued work and active consumers, keeping the native buffer from becoming a download queue.
- Create post-action popovers when opened. Callbacks use the current post snapshot.
- Retain factory clamp widgets while recycling, and use native list separators instead of an extra container/separator tree per row.
- Patch notification read indicators on the existing native rows, retaining model identity, focus and avatar work. Content changes still rebind.
- Index retained model entries by key for counter updates; unchanged control labels retain their widgets and accessibility state. Body/media changes still take the full content path.

Existing native navigation/sidebar/profile/startup transitions and the 160 ms arrival reveal remain. Motion follows GTK's animation preference; reduced-motion runs keep scrolling/input functional while skipping nonessential transitions. No forced renderer or system power-profile change is installed.

## Results

Measured on 2026-10-28 with the installed x86_64 GNOME 51 app, GTK 4.24.1/libadwaita 1.10.0/Python 3.14.9, Wayland, a 59.998 Hz display and the default Vulkan renderer. These are single sequential sampled runs, not statistical confidence intervals or cross-device promises. [Aggregate results](performance-results.json) retain every phase, including outliers.

| 250-post stress operation | Before | After |
| --- | ---: | ---: |
| FeedView counter batch: synchronous action | 90.9 ms | 14.0 ms |
| Initial model insertion: synchronous action | 550.4 ms | 471.9 ms |
| Open conversation: worst measured frame span | 687.3 ms | 656.3 ms |
| Open profile: worst measured frame span | 653.5 ms | 629.8 ms |
| Show search results: worst measured frame span | 650.5 ms | 623.0 ms |
| Peak process RSS over full stress sequence | 434.3 MiB | 384.2 MiB |

| Continuous scroll | 30 posts, 1100 px | 30 posts, 480 px | 250 posts, 1100 px | 250 posts, reduced motion |
| --- | ---: | ---: | ---: | ---: |
| First feed sweep | 59.75 fps | 59.25 fps | 36.90 fps | 57.76 fps |
| Reverse feed sweep | 60.00 fps | 59.50 fps | 36.71 fps | 54.20 fps |
| Conversation | 58.74 fps | 59.25 fps | 34.00 fps | 56.50 fps |
| Profile | 58.74 fps | 59.50 fps | 34.25 fps | 59.25 fps |
| Search | 60.00 fps | 60.00 fps | 35.65 fps | 58.49 fps |

Three separate startup-only trials measured 630.6, 644.4 and 639.5 ms from Python-process creation to first frame, including imports/application construction. The corresponding application-loop-to-frame timings were 166.6, 166.8 and 164.0 ms. These warm-host trials do not include the earlier Flatpak launcher or establish disk-cold/login-keyring/network startup latency.

The normal-sized sweeps are near 60 fps, with occasional missed intervals; the dense animation-enabled sweeps are around 34–37 fps. Cold dense views still have roughly 0.6-second frame spans. The target of 60 fps at all times is **not met**.

Counter updates improved from 90.9 ms to 14.0 ms in the deliberately excessive all-post update. Shared warm images needed no worker image calls during dense view construction, compared with 179 calls for the initial feed before the changes. This is avoided work, not a claim about live download throughput.

The plain-label control reached 60 fps on its forward sweep. OpenGL dense scrolling remained around 36–38 fps. Diagnostic runs changing focus, disabling CSS transitions, setting label-revealer duration to zero or removing overlay scrollbars did not remove the dense-scroll cost; none of those diagnostic overrides is installed. An idle audit found no live Skyloom tick callback, spinning loader, active stack transition or arrival CSS class. Reduced motion improved dense scrolling considerably; native animation/layout work still needs deeper attribution, and no specific upstream bug is asserted.

GTK 4.24.1 has a [200-item native list buffer](https://github.com/GNOME/gtk/blob/4.24.1/gtk/gtklistview.c#L33), plus tracker extras. The stress run retains about 205 bound post rows per large view. This identifies a concrete remaining optimisation target: lighter/reusable cells and allocation work, while retaining all messages, native focus/accessibility and accurate reading anchors.

### Editing, notifications and dialogs

A supplemental installed interaction run covers a demo reaction roundtrip, a 300-character draft/autosave, four local image previews, 100 notifications and Mark seen, menus, Preferences, image viewing and offline/online control changes. Draft editing/save had a 1.6 ms p95 measured frame span; four previews had 2.3 ms p95 in the first supplemental pass. Notification scrolling stayed near 60 fps. These remain fixture and cached-image workloads, with the physical-input/network limits described above.

The first supplemental pass exposed avoidable read-state work: marking 100 records seen caused 100 binds/unbinds and a 266.7 ms maximum presentation gap. In-place updates removed those rebuilds. **Correction:** a presentation gap during this static asynchronous operation does not establish a main-thread stall: the demo service deliberately waits 60 ms. Keep those historical raw results, but do not interpret the final 100 ms gap as 100 ms of blocked rendering. The continuation below measures the completion callback directly. Changed notification content still rebuilds normally.

The reading matrix/startup samples were collected on build `47c44a6f…`; the isolated notification update was then measured on final build `9bce2be0…`. The post/media rendering paths are unchanged between those two builds. Exact commits, configurations and phase aggregates are in the results JSON. Occasional GDK frame-timing warnings, including a discarded-frame warning in the final interaction pass, remain visible in the local logs; these measurements are estimates from the available presentation feedback, not GPU/kernel tracing or a frame-perfect acceptance guarantee.

## Performance and battery continuation

The installed continuation build `11ef6fb3…` replaces minute-by-minute refresh polling with one suspend-aware deadline. There is no refresh timer while inactive, editing, offline, metered without permission, in power saver, showing a dialog, or waiting for a request. Completion/focus/network events reconsider eligibility; unrelated worker completions retain an unchanged deadline. A native test verifies one-shot timerfd scheduling, stable deadlines, completion rearming and power/focus gates. Python documents [zero-interval timerfd as one shot](https://docs.python.org/3.14/library/os.html#os.timerfd_settime); CLOCK_BOOTTIME includes suspend without a hardware wake alarm.

Uncached viewport media and automatic paging wait while inactive. Reactions gain an accent and a 160 ms ease-out opacity response only when the viewer's selected state changes; counts and server acknowledgement do not replay it. Notifications retain a fixed-size unread envelope and expose read state to assistive technology, with no caption reflow or corrective scrolling. Feedback only animates in the visible clip, releases completed animations, finishes on unmap/inactivity/power saver, and follows both the legacy animation switch and [GTK's reduced-motion preference](https://docs.gtk.org/gtk4/property.Settings.gtk-interface-reduced-motion.html). Native transitions and existing arrival feedback remain.

[Continuation aggregates](performance-continuation.json) retain same-session baseline and final installed fixture results. Marking 100 notices read retained all model objects and the exact reading position, with zero binds/unbinds. Its main-thread completion measured **17.284 ms**, with a worst paint span of **10.589 ms**; total phase CPU was **97.475 ms**, including other threads and animation. Initial creation of the 100-notification view remains heavier: its completion measured **86.499 ms**. Reaction completion was **4.821 ms** and its worst paint span **14.761 ms**. These are single samples, not universal bounds.

Eight seconds of quiet mapped idle used **0.177 ms process CPU**, one voluntary context switch and no paint frames (baseline: 0.224 ms, one switch, no paint frames). The unmapped sample, including hide, used 13.956 ms CPU and one paint span. This confirms no periodic painting in that short quiet sample; it cannot establish laptop energy savings. The deadline test establishes avoided minute polling structurally, rather than inferring it from an eight-second run.

A fixture-only Sysprof trace captured GTK marks, without system-wide counters, kernel stacks or hardware energy sampling. It confirms a remaining cold layout span of **571.72 ms**. Same-session unchanged-baseline scrolling was already near 60 fps, unlike the earlier 34–37 fps runs above; that difference is unexplained and must not be attributed to this continuation. Cold row construction and initial notification work remain open. Capture conditions and all raw aggregate phases are retained so these observations do not erase the earlier slow runs.

## Card interaction refinement

Installed build `90325456…` uses natural-width profile/label targets, local child-control focus rings and consistent symbolic action/count controls. Count updates retain their image/label widgets; constructing the controls directly avoids creating and immediately discarding three icons for every post in the native row buffer. No production renderer preference changed.

The final 30-post scrolling sample measured **59.75 fps** forward and reverse, with maximum paint spans of 6.614/3.565 ms. The final 250-post sample measured **51.68/42.93 fps**, with a 632.012 ms cold construction frame span. A preceding card sample measured 54.69/51.20 fps; the earlier performance-pass reference measured 57.49/53.44 fps. Conditions on the shared host are not a controlled A/B, and no FPS gain is attributed to the allocation change. These results retain the missed-frame cases and cold-view limitation, rather than claiming universal 60 fps. [Card aggregates](performance-cards.json) preserve all four runs, including the normal page and dense tails.

## Upper-edge and update overlays

The new scroller wrapper draws its child directly at zero offset. During a 360 ms upper-edge peek it clips/translates the cached child snapshot, without changing model/scroll/allocation state. New-item notification presentation uses a coalesced notice-only idle callback; it does not queue media/paging scans on focus changes or reserve banner height.

A final installed 30-post normal scrolling sample measured **59.23/59.73 fps** forward/reverse, with maximum paint spans of **8.186/5.221 ms**. [Aggregate results](performance-peek.json) retain all phases and the exact build. This is ordinary scrolling through the new wrapper, not a controlled comparison or a claim about hardware battery savings/60 fps peek animation. Native tests and peak/rest fixture captures separately verify animation progress/end, clipping, motion/power/activity gates and unchanged reading geometry. Dense/cold-view limitations above remain open.

## Adversarial refactor measurements · 28 October

[Refactor aggregates](performance-refactor.json) preserve the installed 30-post run, the rejected baseline, storage work counts and a separate image-retention experiment. The final X11/default-renderer candidate measured **58.24/57.49 fps** in forward/reverse scrolling, with 234/230 frame-work samples, p95 work **11.306/11.143 ms** and maximum work **17.495/17.696 ms**. Cold list creation still had a **101.160 ms** frame-work span. No universal 60-fps claim is made.

The pre-change baseline had only four warm-scroll frame-work samples and different travelled distances. The comparator rejects it for insufficient samples and mismatched work, and also reports larger candidate CPU totals. Those totals compare different delivered workloads and cannot establish a CPU regression or improvement. An attempted Wayland baseline likewise lacked adequate scrolling feedback. Obtain a matched, well-sampled baseline before claiming relative timing acceptance; the current candidate is a standalone measurement. No production renderer, compositor security or system motion preference was changed.

An unchanged 250-post reading window now saves a position with **one bookmark serialization, zero post serializations and one changed SQLite row**, compared with 251 serializations and 501 changed rows in the original probe. Repeating the unchanged bookmark changes zero rows. Cached URI lookup now uses `feed_posts_uri_age` rather than scanning/sorting the archive. These deterministic work reductions have required regressions; they are not stopwatch claims.

The image experiment uses 64 distinct locally generated 1024×768 PNGs, real native Pictures and separate processes. Simulated former retain-all ownership held **64 paintables / 192 MiB estimated decoded pixels**; current viewport ownership held **12 paintables / 48 MiB**. Both modes released all tracked consumers/textures after explicit cleanup. Peak process RSS was **112.88 MiB versus 113.67 MiB**, so the experiment establishes reduced references/estimated residency, **not lower whole-process RSS**. Pixel accounting excludes decoder/renderer copies, and solid generated PNGs are not a live photo-heavy feed. The old mode is an explicit simulation using the current decoder, not an old installed binary. No hardware energy measurement was taken.

## Remaining work

Cold view construction and remaining missed-frame cases must be assessed against the measurements above, with production-sized and maximum-sized snapshots kept separate. Validate on more hardware, photo-heavy live feeds and high-refresh displays before making a broad smoothness guarantee. Physical gestures, Orca and authenticated-service acceptance remain separate gates.

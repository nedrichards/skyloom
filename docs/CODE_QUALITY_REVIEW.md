# Adversarial code quality and design review

Review date: 28 October 2026. Scope: the current checkout and the delivered `566ec8b0` Flatpak, before GitHub publication. Three delegated read-only workstreams examined state/storage/service ownership, rendering/performance, and interaction/controller/test design. The primary reviewer checked the call paths and reproduced the findings below using invented records. The original review itself changed no production code, installation or bundle; the resolution below describes the subsequent authorised implementation. No account data or credentials were accessed, and nothing was published.

The principal opportunity is to **give each operation one owner and remove its competing representations**. File length alone is not a reason to split a module. Several concrete faults already arise where a second path bypasses the first owner's invariants.

P1 means fix before publication; P2 means a valuable bounded refactor or validation improvement; P3 means remove retired concepts after the relevant path has regression coverage. These are review priorities, not claims that proposed fixes have shipped.

## Resolution

The review findings below are retained as the original evidence. Implementation now gives storage IO, model replacement/indexing, request completion and list positioning explicit owners. The following table supersedes the original “unresolved” status; final build/test measurements are recorded in DELIVERY_REPORT and BUILD_ENVIRONMENT.

| Finding | Implemented resolution | Regression evidence |
| --- | --- | --- |
| R1 | Account epochs are checked inside the storage IO lock shared with clear. Queued local operations capture their account before they start. Blocking keyring work is drained across repeated cancellation while retaining SDK ownership; failed cancelled refresh saves still require persistence recovery. | `test_storage_lifecycle.py`: cancelled identity/draft/feed/checkpoint jobs, account replacement, secure-write/clear ordering and cancelled save failure. |
| R2 | One keyed reconciliation accepts presentation invalidations and rebuilds its row index after replacements; conversation and feed adjacency no longer splice behind that index. | Parent discovery followed by visible reaction/count changes retains index identity and body widgets. |
| R3 | One current Undo toast/action token; old toast buttons cannot consume its replacement. | Old/current clicks and existing view/account/reaction/jump Undo contracts. |
| R4 | `request_scope.py` owns slot identity, account/generation and page liveness for feed/profile/search/notification/draft reads. A popped page retires immediately, including its outgoing transition; mutation presentation callbacks are guarded without retrying server mutations. | Deterministic queued A/replacement B, closed/transitioning page and account/generation tests. |
| R5 | Shared incoming-URI/metadata helpers keep named pager transitions distinct and remove bridge duplicates. | Duplicate bridge and existing bound/anchor/real-cursor regressions. |
| R6 | Bookmark-only updates use a small separate table. Immutable window comparisons archive changed posts only and update protection only when membership changes. Heads contain URI references. Migration inserts missing legacy payloads without overwriting newer records. | Unchanged 250-post position save: zero Post serialization and one changed SQL row; legacy/fresh-network migration test. |
| R7 | `(uri, touched DESC)` index matches cached-post lookup. | Actual query-plan assertion rejects archive scans and temporary ordering. |
| R8 | FeedView owns cancellation of every list's pending positioning; header and post correction share the input serial. ReadingSession only captures/checkpoints durable position. | Header restore cannot override later input; feed/restart/padded-fragment/Undo tests remain. |
| R9 | Profile data/cursor/busy aliases removed. RecordPager shares bounded people/notice cursor bookkeeping. FeedCoordination owns transient startup/arrivals/gaps. One refresh decision drives both commands and the production monitor. Request presence, rather than a pager's loading presentation, owns actual profile IO activity. | Record cursor/dedup tests, actual monitor integration and native second-profile-page regression. |
| R10 | Decoded cache is limited by 48 MiB and 32 entries. Weak consumer accounting tracks actual bound textures. List consumers release outside a viewport margin/unmap, preserve picture geometry and reload on return; stale callbacks and completed futures cannot retain/reinstall released images. | Byte/count/account/weak-ownership tests; native offscreen picture test; distinct-image retention experiment in PERFORMANCE. |
| R11 | Required-runtime gate rejects missing display/empty discovery/unexpected skips. Versioned performance comparisons check matching environment/workload, timing/work/CPU/RSS and missing/insufficient scroll samples. Named smoke scenarios have cleanup, alongside the full journey; preferences captures include the real native chooser. | Gate failure tests and strict native/runtime/GUI evidence. Controller focus uses GTK's within-window `is_focus`, not compositor-global focus; activity is an explicit policy fixture input. |
| R12 | Retired freshness/offline/result fields removed. CachedFeed has an explicit Pager type in the domain module; compatibility fields remain only in the decoder. Cached-feed smoke targets the actual cached-state API. | Cache-first/offline/restart/legacy contracts and full smoke. |
| R13 | Appearance chooser's arrow and contents use one matching theme border and an outer shadow, avoiding the extra inset seam. The override is scoped to that chooser. | Native light/dark and high-contrast captures, wide/narrow settings interaction checks. |

The change does not shrink the disk archive, add an automatic mutation queue, change the app-password route or claim universal 60-fps rendering. Measurement quality is a gate: a compositor-throttled run with insufficient scroll samples is rejected, even when that prevents a timing comparison from passing.

## Findings requiring correction

### R1 · P1 · Cancelled filesystem work can recreate signed-out data

Evidence: [Service.save_feed_state](../src/skyloom/service.py#L203), [feed cache writes](../src/skyloom/service.py#L179), [sign-out](../src/skyloom/service.py#L148), [Worker cancellation](../src/skyloom/worker.py#L83).

The account-object check precedes `await asyncio.to_thread(...)`. Cancelling that coroutine releases the service's async lock while an already-running filesystem thread continues. Sign-out can acquire the lock, clear the database and reset the account; the old thread can then open the database and write after the clear. Checking the account before submitting the write is insufficient.

**Reproduced in the supported Flatpak runtime:** gate an invented checkpoint before database opening, cancel its service coroutine, perform the same clear/account-reset sequence under the service lock, then release the thread. One cached post reappears. The probe deliberately excludes keyring and server-revocation calls and uses a temporary directory.

**Simplifying refactor:** enforce account epochs and write/clear exclusion at the actual storage IO boundary. [ImageCache.write/clear](../src/skyloom/image_cache.py#L79) already provides a local example of token validation within an IO lock. An alternative must await thread completion before releasing ownership on cancellation; merely adding `asyncio.shield` does not accomplish that. Retain SDK/auth serialization, but stop treating its coroutine lock as ownership of a separately running thread.

**Required validation:** gated cancellation after IO starts for checkpoints, feed-cache writes and other account-file writers; sign-out followed by re-sign-in to the same DID; prove no old-generation data can reappear. Do not queue or retry server mutations as part of this change.

### R2 · P1 · Conversation presentation changes detach the row index from the model

Evidence: [ConversationView.sync](../src/skyloom/conversation_view.py#L197), [keyed model reconciliation](../src/skyloom/widgets.py#L649), [counter updates](../src/skyloom/widgets.py#L798).

`set_items` rebuilds `entries`, then ConversationView performs further direct model splices when parent/opened/branch presentation changes. Those replacements do not update `entries`. A subsequent reaction/count update updates a detached PostObject instead of the visible model object.

**Native reproduction:** run the existing cached-message/parent-discovery fixture, then update that post's likes. The indexed object differs from `model.get_item(index)`; the indexed value changes and the visible model value does not.

**Simplifying refactor:** one model reconciliation path must own both replacements and the index. Pass explicitly invalidated presentation keys into that path, or use a small atomic replacement helper. Feed adjacency changes currently also perform a second replacement pass; include them in the same reconciliation operation so each affected row rebinds once.

**Required validation:** after every parent/branch/adjacency update, indexed object identity must equal model object identity. Then exercise reaction success, rollback and server-count refresh, retaining the body/media widgets for counter-only changes and preserving child focus.

### R3 · P1 · An older Undo toast invokes a newer action

Evidence: [Interactions.offer_undo/undo](../src/skyloom/interactions.py#L272); compare the existing stale-toast guard in [UpdateNotice](../src/skyloom/list_feedback.py#L167).

Every Undo toast calls `self.undo()`, which consumes the latest global `undo_action`, rather than the action advertised by that toast. With two successive actions, clicking the older toast undoes the newer one.

**Native reproduction:** offer two invented callbacks and emit the first toast's button signal; only the second callback runs.

**Simplifying refactor:** own one current Undo token and toast. Dismiss/retire its predecessor and bind clicks to the captured token. Keyboard Undo should deliberately target the latest token. Reuse the ownership rule already established for update notices without merging their different product semantics.

**Required validation:** old/current toast clicks, repeated Undo, reaction followed by jump, view change and account-generation change. A stale control must never execute a different action.

### R4 · P1 · Request completion guards are repeated and inconsistent

Evidence: [generic page_load](../src/skyloom/window.py#L986), [feed completion guards](../src/skyloom/window.py#L605), [profile completion/failure](../src/skyloom/window.py#L1456), [follow/moderation callbacks](../src/skyloom/window.py#L1494), [GLib dispatch](../src/skyloom/worker.py#L58).

Feed handlers check future identity before removing a request. Generic page loading removes the slot without checking whether it still owns it. Profile failure lacks its success path's page/generation checks, and follow/moderation callbacks are not scoped to page/account liveness. Cancellation cannot revoke a completion already queued to GLib. An old queued callback can therefore remove a newer request slot or update a page/account context it no longer owns. The moderation completion additionally renders and refreshes the current feed.

**Deterministic reproduction using the actual `page_load` method:** retain A’s completion callback, start B, then dispatch A. A still applies and removes B’s request slot. The profile/follow/moderation variants were traced statically rather than separately exercised.

**Simplifying refactor:** a small request-owner/token mechanism should contain request identity, account generation and page liveness, and own replacement/retirement of its slot. Apply it first to page reads. Mutation callbacks need a liveness token for presentation; do not imply cancellation reverses an accepted server mutation or introduce automatic retries.

**Required validation:** complete A, start B before dispatching A's callback, then dispatch A. Repeat with page removal, filter change and sign-out. Neither success nor failure may clear B or update the wrong page. Existing cancellation tests mostly cancel still-running work and do not cover this queued-completion boundary.

### R5 · P1 · Gap bridging violates the pager's unique-URI invariant

Evidence: [Pager.bridge](../src/skyloom/domain.py#L184), compared with the incoming-record deduplication in `merge`, `appended` and `reconciled`.

Bridge additions are filtered against the existing prefix/suffix, but not against earlier additions in the same incoming page. An invented `(new, new, overlap)` bridge produces four records with only three unique URIs. This conflicts with URI-keyed row indices and the protection table's primary key.

**Simplifying refactor:** share the invariant helpers for unique incoming records, retained-key metadata and real cursor boundaries across pager transitions. Keep append, live-head reconcile, explicit reorder and bridge as named operations with different semantics; do not turn them into an opaque collection of mode flags.

**Required validation:** duplicate bridge pages and table-driven/property-style checks for unique URIs, capacity, reader retention, repeated/no-progress cursors and continuation cursors drawn only from real request boundaries.

## Refactors with performance and comprehension benefits

### R6 · P2 · Position saving serializes and rewrites unrelated content

Evidence: [ReadingSession.snapshot/flush](../src/skyloom/reading.py#L94), [Storage.checkpoint](../src/skyloom/storage.py#L194), [archive serialization](../src/skyloom/storage.py#L106).

Moving only the bookmark in an unchanged 250-post window caused **251 `asdict` calls and 501 changed SQLite rows** in an instrumented temporary database. The conditional post upsert avoids unchanged payload writes, but not full serialization, rewriting the feed/head JSON, or deleting/reinserting all protection memberships. The operation also holds the SDK service lock.

**Refactor:** distinguish content/window revisions from bookmark revisions. Persist position as a small independent update; archive changed posts on fetch/reaction changes and change protection only when window membership changes. Replace the second full head-payload copy with ordered URIs when undertaking the storage migration. Preserve atomic window/bookmark updates when the window actually changes.

**Validation:** zero post serialization and zero protection-membership changes for bookmark-only saves; bounded/coalesced writes under scrolling, final pre-unmap/shutdown persistence, readable legacy caches and reaction durability. Measure serialization time, SQL changes and request latency before claiming a battery or frame-rate improvement.

### R7 · P2 · The archive lookup index does not match the lookup

Evidence: [schema](../src/skyloom/storage.py#L57), [cached_post](../src/skyloom/storage.py#L292).

The primary key is `(feed, uri)` and the other indices concern age. The URI-only lookup ordered by `touched` has an actual query plan of **`SCAN feed_posts` plus `USE TEMP B-TREE FOR ORDER BY`**.

**Refactor:** add the specific `(uri, touched DESC)` lookup index first. A larger canonical-post/feed-membership normalization can follow if R6 warrants it; it is not needed to fix this query.

**Validation:** query plan plus cold hit/miss lookups using a 50,000-record invented archive, accounting for index build/write cost. Keep account isolation and quoted-post lookup coverage.

### R8 · P2 · Scroll correction is partly owned by persistence

Evidence: [header versus post restore](../src/skyloom/list_interaction.py#L176), [FeedView.user_input](../src/skyloom/widgets.py#L593), [ReadingSession.input](../src/skyloom/reading.py#L51).

Post restoration checks `input_serial`; header restoration repeatedly applies its old adjustment without that check. Tick cancellation lives in ReadingSession, which exists on home feeds but not on profile/search headers.

**Native reproduction:** restore a header at adjustment 10, signal actual-input handling and move to 400 before the deferred correction. The old callback returns it to 10.

**Refactor:** the shared list owns one interruptible positioning operation for headers and rows, including top/return/settling. Reading persistence captures and serializes positions; it should not own cancellation of generic GTK positioning work.

**Validation:** wheel, keyboard and pointer interruption while restoring profile/search headers and post rows; startup restoration, top/Undo, changed font/width, native boundary clamps and unmap/close cleanup.

### R9 · P2 · Pagination and refresh decisions have mirrored state

Evidence: [profile state](../src/skyloom/window.py#L1318), [search state](../src/skyloom/window.py#L1548), [refresh monitor eligibility](../src/skyloom/refresh_monitor.py#L69), [automatic command eligibility](../src/skyloom/interactions.py#L167).

Profile keeps Pager plus separate posts/cursor/busy values; its posts alias is written but not read. Search and notifications separately repeat cursor-history/deduplication bookkeeping. RefreshMonitor and Interactions independently reconstruct eligibility/busy decisions. ReadingSession also combines persistence with startup reorder policy, arrival counts and gap loading/presentation state.

**Refactor in small steps:** remove dead aliases, choose one owner for page data and request activity, then share only common bounded cursor bookkeeping. Let one pure refresh decision provide target/eligibility/deadline, while the monitor supplies events and the timer. Keep durable checkpoints separate from a feed coordinator that owns ordering, gaps and arrival navigation. This gives a meaningful reason to extract feed coordination from Window rather than merely move methods between files.

**Validation:** repeated cursors, empty intermediate pages, filters/reset/retry, late callbacks and connectivity/cost/power/dialog/editing gates. Exercise the actual RefreshMonitor: the full GUI smoke currently closes it and calls the other refresh entry point directly, so it does not prove production scheduling end to end.

### R10 · P2 · Decoded-photo residency needs an explicit workload and budget

Evidence: [32-entry texture cache](../src/skyloom/media.py#L181), [paintable retention](../src/skyloom/widgets.py#L1187), [existing fixture limitations](PERFORMANCE.md#method).

The LRU limits cache references, but a loaded Gtk.Picture retains its texture until its row unbinds. The large native prefetch buffer can therefore retain more textures than the LRU limit. Existing performance fixtures reuse a few shipped images, so they do not establish a bound for many distinct photos.

This is a structural memory risk, **not a reproduced OOM or measured regression**.

**Refactor only after measurement:** account for resident decoded bytes, choose appropriately sized renditions and release/deactivate media outside a bounded viewport margin while preserving card geometry. Keep the generous encoded disk archive independent from decoded texture residency.

**Validation:** many distinct invented images, live decoded bytes/peak RSS, forward and reverse scrolling, cached/offline reloads, cancellation, reduced motion and media-free list pacing. Preserve shared textures and concurrent-request coalescing.

### R11 · P2 · The test tools are not yet a complete refactoring safety gate

Evidence: [native discovery wrapper](../scripts/test-in-flatpak.sh#L4), native DISPLAY skip decorators, [performance report exit conditions](../scripts/performance-pass.py#L516), [refresh smoke setup](../src/skyloom/smoke.py#L1576).

The native wrapper can report success after GUI tests skip, because unittest discovery exits zero for skips. The performance runner records useful distributions but does not fail for slower timings or additional row/media work; its explicit workload failure is absent scroll movement. Several critical composition cases in R1–R5 and R8 are absent from the normal suite despite individual-feature tests passing.

**Refactor:** distinguish optional host checks from a required-runtime/display gate that rejects unexpected native skips. Add deterministic ownership/invariant tests first. Then add a comparison command with fixed workload/backend/renderer and explicit budgets for bind/image/job counts, idle activity, missing samples and relative timing changes. Do not use an arbitrary universal 60-fps pass threshold on this shared desktop.

Give smoke scenarios explicit setup/cleanup and named selection so a refresh failure can be reproduced without traversing unrelated composer/profile/label scenarios. Retain the complete installed journey as a separate gate. Keep current contracts in FEATURES/ARCHITECTURE, commands in DEVELOPMENT/TESTING, and dated measurements/build IDs in delivery/performance evidence. Some TESTING text still describes the retired staged-feed/data-Undo contract.

### R12 · P3 · Retired refresh fields still expand the mental model

Evidence: [CachedFeed](../src/skyloom/feed_state.py#L53), [startup policy reset](../src/skyloom/window.py#L614), [Service.refresh_stamp](../src/skyloom/service.py#L216), [old smoke monkeypatch](../src/skyloom/smoke.py#L1760).

`CachedFeed.head` and `refreshed` are produced without a production consumer. `Pager.offline` is assigned/copied without a production read; connectivity decisions use Connection. `refresh_stamp` survives as a wrapper and smoke monkeypatch even though initial loading calls `cached_state` and resets policy with `restore(None)`.

**Refactor:** remove unused result fields/state/wrappers and rewrite the smoke around the API actually called by the app. Preserve old stored data only within the compatibility decoder where needed. Use an explicit Pager type for CachedFeed once the module dependency is resolved; avoid replacing concrete domain types with `object` merely to hide a cycle.

## Recommended implementation order

1. Add deterministic failing regressions for R1–R5, then repair storage IO ownership, row/index reconciliation, Undo tokens and request ownership in separate reviewable changes. Share pager invariants and fix bridge deduplication.
2. Move positioning cancellation to the shared list (R8). Remove retired fields and dead aliases while the corresponding tests are clear (R12 and the first part of R9).
3. Split bookmark-only persistence from content/window updates and fix the URI lookup index (R6–R7), with a backwards-compatible cache migration and measured work counts.
4. Consolidate feed/request/refresh coordination (R9), preserving specialised domain transitions. Do this after the invariants and lifetime tests exist, rather than extracting a large controller wholesale.
5. Establish strict native/performance comparison gates and isolated smoke scenarios (R11); use them for the cell/rendition work in R10. Instrument distinct-photo residency before choosing that refactor.

After each semantic change: relevant pure/contract tests, native suite, installed Flatpak functional/GUI checks and affected performance workloads, run sequentially. Compare fixed baseline conditions and retain tail/missing samples. Do not alter expected values to conceal a product regression.

## Concepts worth retaining

- Archive versus rendered window: thousands of encoded records and a bounded native list serve different memory/reading needs. Do not shrink the archive to disguise rendering cost.
- Immutable Post/Page snapshots, real opaque cursor boundaries and the specialised causal conversation graph.
- Page data, cursor bookkeeping and pager presentation have different responsibilities, even where aliases can be removed. Do not merge every list into one generic state machine.
- A serializable neighbour-aware Bookmark and an in-process ListPlace that can identify a native header. Share positioning ownership, not incompatible persistence representations.
- One native content scroller, keyboard/child focus semantics, reduced-motion/power gates and explicit server mutations with no automatic outbox.
- Shared decoded textures, request coalescing and in-place counter updates; the issue is extending their ownership/budgets consistently.

## Original review validation (before fixes)

| Check | Current result |
| --- | --- |
| `check.sh`, source/default renderer under X11 | Lint/format/compilation/desktop/schema pass; 172 tests run, **five focus/motion assertions fail**. Failures concern label focus, quoted Return, native-row focus and two active-animation expectations. These are current unresolved results; this review does not establish that they are product regressions. |
| Explicit X11/Cairo source suite | **172 tests pass**, no skips. This is functional evidence, not default-renderer pacing or physical-input acceptance. |
| Native adversarial probes, X11/Cairo | Confirm detached conversation row/index with lost counter update, stale Undo invoking the newer action, and header restoration overriding later input. |
| Deterministic queued-completion probe | Actual `page_load` applies A and removes B’s slot after B replaces A. |
| Temporary storage/service probes, supported runtime | Confirm 251 serializations/501 changed rows for a position-only save, archive scan plus temporary sort, duplicate bridge URIs and a stale thread recreating cleared cache data. Probe exits successfully. |
| New performance benchmark/full GUI smoke | At the original review stage these were not rerun because no production code changed. Subsequent implemented fixes and final validation are recorded in the Resolution table and DELIVERY_REPORT. |

Local disposable evidence is in `build-runtime/review-baseline-check.txt`, `review-cairo-check.txt`, `review-native-probes.py/.txt`, `review-state-probes.py/.txt` and `review-request-probe.py/.txt`. These ignored artifacts use invented records only. The first probe attempt stopped on a missing stub method; the final native probe completes successfully. The agent's host cancellation probe hit an asyncio shutdown limitation; the primary review reran it in the supported runtime, where it completed cleanly. No failing product assertion was disabled.

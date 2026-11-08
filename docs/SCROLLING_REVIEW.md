# Scrolling architecture review · 8 November 2026

Momentum scrolling is not yet accepted as seamless. This review identifies code
paths and existing measurements; it does not attribute the reported ghosting to
a renderer without a reproduction.

The maintainer's latest retest reports a substantial improvement after the cell
and conversation-loading changes. Visual disturbance when new items arrive during
momentum in a long conversation remains open in [the roadmap](ROADMAP.md).

## Findings and changes

1. **Core reuse implemented; cold construction remains.** `FeedView` retains
   a Clamp from setup and a PostRow shell from its first post bind. Later binds reuse the header,
   selectable text label, actions and controllers; quoted core cells are also
   reused. Unbind clears binding-specific state and media. First-view buffering
   still builds many cells, while label and external-card structures remain item-specific. Avatars/media slots
   are now retained, and warning controls are built only when content is hidden. Existing dense/cold measurements in PERFORMANCE.md are
   historical; no universal frame-budget acceptance follows from core reuse.
2. **Fixed: image failure changed row geometry.** `PostRow.add_image` previously
   hid the 220-pixel image button and appended an error label on asynchronous
   failure. It now retains the Picture/button rectangle and gives it an
   accessible failure description and retry tooltip. Explicit image activation
   remains available. Disabling automatic images also reserves the same height.
3. **Fixed: late paging and unnecessary action presentation.** The automatic
   threshold is now two viewports instead of 0.6, giving a single in-flight
   request more lead time. Healthy paging hides Load more. Errors, no-progress
   cursors, explicit initial loads and policy pauses retain a recovery/override
   action. Empty/duplicate pages still stop automatic traversal rather than
   consuming an unbounded series of network requests. No automatic mutation
   retry or background-policy bypass is introduced.
4. **Medium: viewport scans scale with the native buffer.** Every coalesced
   two-frame check walks all media bindings and computes mapped widget bounds;
   visible-row probes separately serve prefetch, gap loading and reading anchors.
   Native mapping alone does not imply viewport visibility. Consolidating row
   geometry per frame is worth measuring, preserving the separate load/release
   margins and stale-callback guards. Deferring every scan until scrolling stops
   would leave fast scrolling with blank images and late paging.
5. **Medium: reading checkpoints run during sustained scrolling.**
   `ReadingSession.changed` starts a one-second timer without resetting it on
   further movement. Thus a long momentum scroll can capture visible geometry
   and copy the retained pager on the main thread once per second. SQLite IO is
   correctly on the worker. Measure this separately before replacing it with a
   settle debounce: navigation/unmap/shutdown still need immediate durable
   checkpoints, and continuous reading must not lose all progress on a crash.
6. **Unproven: snapshot/compositor artifacts.** TopPeek has a direct snapshot
   path at rest and resets on movement. There is no evidence here that forcing
   Cairo/full redraw would fix the reported symptom. Do not change the default
   renderer or globally disable native motion based on this review.

## Validation needed for visual acceptance

Use invented distinct-image feeds at 30 and 250 posts, narrow/wide windows,
large text and reduced motion. Record row bind durations/counts, main-thread
frame-work tails, travelled distance, image residency and request counts during
fast forward/reverse momentum gestures. Include cold/decoded-cache/encoded-cache
passes and delayed/failed page/image completions. Compare matched workloads;
existing reports are context, not a fresh before/after baseline. Check exact
visible-post offsets, selection, keyboard/Orca access and return navigation.

A human physical-input review under the normal Wayland renderer is required
before calling ghosting resolved or claiming perfect scrolling. Native functional
tests establish invariants, not compositor presentation quality or network
latency guarantees.


## Four-target follow-through

The implementation now removes the one-character body-width measurement path,
retains avatar/media/core parent chains, uses local action CSS classes, avoids
unchanged metadata/Post DTO allocations and plain-text facet temporaries, and
constructs warning controls on demand. These are verified work reductions, not a
claim that every frame meets budget. First-view buffer population still creates
about 205 cells in the 250-post fixture. Repeated viewport scans, external-card
and disclosure construction, and remaining cold model-install latency deserve
further investigation. See the current [performance evidence](PERFORMANCE.md).

## Conversation-loading follow-through

Late responses no longer restore the position saved at request start. Status-only
updates retain loader widgets and decorated posts; unchanged prefixes and appends
below the reader need no viewport correction. Recent wheel/kinetic input suppresses
competing background corrections. Branch geometry owns automatic conversation
loading, with directional reply lookahead and a three-request budget renewed by
reading progress. The single-request and retained-message bounds remain. See
[the delivery report](DELIVERY_REPORT.md) for native and installed GUI evidence
and the remaining physical-input acceptance limits.


## Cross-view consistency audit

The header selector is committed separately as `da9f783`. The follow-up audit
traced every content surface rather than treating all timelines as identical.

| Surface | Audited behaviour and changes |
| --- | --- |
| Home / every pinned feed / offline replay | Shared reusable post cells, bounded media and two-viewport paging were already in place. Removed unconditional completion-time scroll corrections. Shared delta handling now preserves static anchors for changes/removals while leaving appends and active momentum to native anchoring. Gap busy/error controls update in place. |
| Conversations | Retains its specialised projection, in-place loaders, directional lookahead, current-anchor comparison and focus recovery. Explicitly opts out of the generic correction so it never schedules two competing restores. |
| Profiles, including Posts / Replies / Media | Already used shared reusable post cells and one scroller. Paging now uses the reader-anchored bounded Pager append path rather than unconditional head trimming. |
| Search posts | Previously constructed PostRow trees for every bind. Now uses the same retained post/quote/avatar/media cells and thread-decoration path as other post timelines. Paging also protects the current anchor and real cursor. |
| Search people | Now retains native action-row and avatar widgets across binds. Its bounded record pager protects the reader and rewinds a partially retained page to the actual request cursor. |
| Notifications | Retains fixed read-marker geometry and in-place Mark seen updates. Now recycles row/avatar shells and protects current anchors/cursors when loading beyond the record limit. Automatic refresh still offers its explicit update action. |
| Drafts | One native scroller with at most 100 local, text-only draft actions; one guarded snapshot load, no incremental timeline insertion or media decode. No timeline-specific correction/recycling change is needed. |
| Image viewer | One scroller containing the image, full description and copy action; bounded image rectangle, worker decode and closed-dialog guard already apply. |
| Composer, Preferences, About, shortcut help, welcome/sign-in | Native bounded forms/dialogs, no append-driven timeline. Existing main-thread widget work, asynchronous service/storage and lifecycle guards remain. |

The generic list captures its current visible key/pixel offset at completion,
not at request start. It corrects static prepends, rebinds and removals, including
removing a gap below the visible prefix: GTK can otherwise change its internal
anchor. Focus transfers before a focused row is unbound. Plain appends,
reaction/read-state patches and active input-led momentum issue no corrective
scroll request. Existing input serials still cancel a pending correction after
new input. The conversation path retains its own finer-grained loader rules.

A passive native touch gesture observes activity and cancellation by the native
pan, extending the shared kinetic interval without claiming input or changing
pull-refresh semantics. Physical touchscreen and default-renderer acceptance
remain required; this is not a claim that the reported compositor artifact is
universally resolved.

Native list slots allocate post cells on their first post bind and retain them
thereafter. People/notification rows never construct unused PostRow trees.
Unbind cancels requests, clears retained avatars and invalidates stale callbacks;
teardown releases both post and record cells. No renderer override, global
animation change, reduced history limit or new API was introduced.

Validation and remaining limits are recorded in the current delivery report.
The existing geometry-scan, checkpoint and cold-construction measurement work
above remains relevant; this audit does not turn those open measurements into
performance claims.

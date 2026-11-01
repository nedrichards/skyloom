# Changelog

## Unreleased

- Shorten position Undo toasts to two seconds and dismiss them when leaving the window, keeping keyboard Undo available. Use “Moved to top” for an explicit top jump, avoiding stale “Back at the top” feedback on resume. Reaction Undo retains its five-second timeout.

- Establish private GitHub source hosting, including the implemented preview and latest thread-context/input improvements; retain the separate public-release and human-acceptance gates.

- Share thread position pills across feed, profile, search and quoted cards. Keep bounded relationship knowledge across views, update mounted pills in place and mark incomplete context with + without fetching threads in the background.
- Let a normal card-text click tolerate small pointer movements. Deliberate drags, double-click word selection, Shift-click selection, existing selections and links retain their native behaviour.

- Show a subtle position pill beside each conversation post's timestamp, such as 1/6. Count loaded posts in reading order, update as context arrives and mark incomplete conversations with +; expose the meaning to assistive technology.

- Slide the sidebar away when resizing into the narrow layout, using the native spring transition after the breakpoint handoff. Animate its return on widening, allow resize reversals and preserve native focus/menu behaviour. Skip the resize motion when reduced motion or disabled animations are requested.

- Announce each pending update batch once. Menus, page changes and window activity no longer replay an existing notice; repeated offers keep the current action without replacing its toast. Unchanged feed refreshes do not reannounce older pending posts, while genuinely distinct batches can still announce even with the same count.

- Prepare the source tree for sharing: strengthen local-file and credential exclusions, restrict screenshots to reviewed demo directories, document the repository audit and its Git-history limitation, clarify local installation and contribution expectations, and make GPLv3-or-later licensing explicit in package metadata and a project licence notice.

- Resolve the adversarial review: cancellation-safe account storage/secure persistence, atomic conversation row/index updates, owned Undo/request callbacks, unique gap records, interruptible header positioning and shared cursor/refresh state.
- Separate bookmark-only writes from post/window persistence, index URI lookups, preserve fresh payloads during legacy migration, remove retired state and bound decoded media/viewport ownership.
- Require native runtime/display coverage with no unexpected skips, add named GUI scenarios and matched performance comparison gates, and fix the Appearance popover's border/shadow seam without restyling unrelated popovers.

- Retain the original adversarial review and its reproduced defects alongside the implemented resolutions and regression evidence.

- Archive thousands of feed posts/pages locally with automatic age/count cleanup and protected reading windows. Persist per-feed post/offset/selection/neighbour positions, replay complete cached pages offline and guard account/lifecycle writes.
- Insert background arrivals immediately while preserving existing order and the reader's position. Accept refreshed ordering on restart or manual refresh, retain non-overlapping history behind explicit paged gaps, and make Go to top/Undo navigate without rolling back refreshed data.

- Use a normal plus button for New post in the header; reserve the suggested-action accent for Post inside the composer.

- Replace the full-width new-item banner with a page-scoped native toast (Go to top for feeds, Show for notifications) that leaves the viewport unchanged. Keep navigation after dismissal, with Show new items in the menu and Ctrl+Shift+Home. Add Brooklet-style, damped upper-edge feedback for wheel/no-op keyboard/top navigation; retain native smooth/touch overscroll and respect reduced motion, inactivity and power saver.

- Refine post cards with compact avatar/profile targets, natural-width wrapping label controls, quieter metadata and consistent symbolic action/count controls. Reserve the card cursor outline for direct keyboard focus; child controls retain their own rings and pointer selection has no full-card wash. Preserve profile focus through conversation content refresh and bundle original outline/filled symbolic hearts.

- Schedule automatic refresh with one suspend-aware deadline instead of a minute poll; resume from activity, focus and worker completion, and pause paging/queued media in inactive windows.
- Keep notification text and row geometry stable when read state changes; use a fixed envelope indicator and an accessible description. Add brief opacity feedback and accent styling for reactions and unread indicators, respecting both GTK motion settings, power saver, inactivity and recycling.

- Add a reproducible native frame/presentation, CPU, memory and allocation performance pass. Share decoded textures and concurrent image work, load uncached media near the viewport, build post menus lazily, recycle native row wrappers and index reaction updates. Marking notifications seen updates existing rows and preserves focus. Preserve native transitions, reduced motion, focus and cancellation/account boundaries. Detailed measurements and remaining frame-budget misses are in `docs/PERFORMANCE.md`.

- Make Show new posts and manual refresh preserve overlapping loaded history and its pagination cursor. Reuse unchanged tiles, patch reaction counts in place, jump to the newest post after layout settles, and reveal visible arrivals with a short opacity-only transition. Respect reduced motion and user input; Undo restores reading position while retaining local reactions.

- Keep profile actions and the post filter in one natural wrapping row. Move the signed-in profile card to the sidebar footer and make it the Profile destination, replacing the separate navigation button while preserving Ctrl+4, pane focus and double-tap-to-top.

- Implement connected conversation rendering with causal oldest-first branches, explicit parent links/opened-message state, unavailable gaps and local loading/retry controls. Preserve deeper branches on refresh, viewport/selection/control focus and local reactions; add scoped parent/first-reply keys and Return/Undo. Join verified adjacent same-author feed previews while every comment opens its exact URI in conversation context.

- Stop feed/connectivity updates rebuilding every mounted post and restarting media jobs. Update reaction sensitivity in place, skip unchanged connection work, preserve the selected feed during metadata refresh, cancel recycled avatars and recheck queued media cache hits. Distinguish local worker saturation from Bluesky rate limiting.

- Prevent repeated activation of the current conversation from pushing duplicate pages or restarting requests; preserve reading position and navigation between different posts.

- Replace raw content-label headings with wrapping icon chips, readable names, scope and explanation popovers, exact-value copying and label preferences. Add a clearer hidden-content card, native reveal transitions and shared visibility choices across mounted copies; keep labelled content visible by default.

- Keep startup neutral until saved-session lookup resolves; delay loading feedback by 200 ms, use a short native crossfade, and offer a distinct recovery view on lookup errors. Cancel startup timers and stale callbacks on close.

- Fill Search with a readable, viewport-sized prompt and loading/empty/error states; preserve one scroller, keep retry/empty-page loading available, and restore the prompt when clearing a query.

- Keep a single visible overflow menu when hiding, showing or resizing the sidebar; route F10 to its current location and close popovers when their menu is hidden.

- Simplify Preferences into Reading, Updates, Storage and Authentication; move Sign out from the overflow menu to the final authentication group, preserving confirmation and return focus on cancellation.

- Preserve saved post content offline and open new/reply/quote drafts without a connection; restore drafts reliably even after many cleared drafts.
- Add a private bounded disk image cache, restart/offline loading, corruption recovery and sign-out cleanup with late-download invalidation.
- Load pinned-feed snapshots before network requests, keep server failures separate from offline state, update account action sensitivity on connectivity changes, and reconcile visible notification read state.
- Retire the bootstrap prompt/runner and consolidate maintenance documentation, implementation evidence and the future roadmap.

- Fix the navigation toggle in wide windows; bind all page buttons to real sidebar visibility, use a closable narrow-window overlay, and preserve content while hiding/showing navigation.

- Move Preferences and About into the header overflow menu, and credit Nick Richards in About, creator credits and AppStream metadata.

- Compose profile details, complete biography, controls, filters and virtualised posts into one scrolling page; transition to a compact profile identity in the toolbar while reading.
- Scroll search fields with results, retain field state/focus through list recycling, and keep long image descriptions reachable in the image dialog.
- Preserve header and post reading positions through top/Undo, refresh and Back; retain native keyboard indices and paging for empty and populated pages.

- Adopt the refined Open Loom app icon and matching symbolic artwork; remove discarded concepts, superseded previews and obsolete icon screenshots.
- Refresh stale visible feeds and notifications while active, respecting connection cost, limited connectivity, power saver, suspend/resume and retry backoff. Preserve reading position with a new-posts banner and Undo.
- Add double-tap/click to top, touch pull-to-refresh, reversible jumps and reactions, native main menus and complete context-aware keyboard navigation with shared shortcut help.
- Keep cached pages and feed choices available on costly/offline startup; pause automatic paging and image downloads while retaining explicit loading actions.

- Open conversations by activating post tiles and quoted cards; remove separate Open/Read controls while preserving profiles, links, image viewers, text selection and reactions.
- Load earlier messages and deeper reply branches as needed, with bounded merging, retry controls, selected-post focus and preserved reaction state.
- Apply consistent inner padding to post and quote content; move image-browser actions into the native viewer.

- Require Python 3.14 and Ruff 0.17.2; expand lint/security/async checks and add a single offline lint command for all sources, tests and helpers.
- Reduce feed-model allocations with slotted dataclasses; simplify ISO timestamp parsing and clarify worker-loop shutdown, contexts and GUI smoke results.
- Stream wheel checksum validation and keep it effective under optimized Python. Isolate and clean up temporary demo drafts.

- Autoload pages near the end of Home, profile feeds, post/people search and notifications, with manual Load more/retry fallback and no automatic retry loop.
- Keep the pager footer in the virtualised list and move scrolling to the full content width. Preserve row identity and scroll position while appending.
- Use dedicated app-password authentication throughout the product documentation and UI. Hide empty image-description sections and irrelevant copy controls.

- Rename the application identity and packaging to com.nedrichards.Skyloom. Remove the obsolete installation, sandbox data, settings and app-specific keyring entries.
- Show labelled posts, quotes, media and profile biographies by default, retaining label notices. Add an optional warning-first preference with in-app reveal controls.

## 0.1.0 — 27 October 2026 (local development preview)

- Add a native adaptive GNOME application, original icons and GNOME 51 Flatpak packaging.
- Wire dedicated app-password authentication, refresh persistence in libsecret, offline restore and sign-out.
- Add Following/pinned feeds, threads, likes/reposts with rollback, profiles, follows, mute/block, search and notifications.
- Add text/reply/quote/image composing, Unicode-safe limits/facets, metadata-stripped uploads, alt text and recoverable local drafts.
- Add offline demo, contract/runtime/GUI tests and fixture screenshots.
- Defer DMs, native video, multi-account use and public publication. Live-account acceptance remains unverified.

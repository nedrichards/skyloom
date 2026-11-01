# Implemented features

Skyloom is a local development preview maintained by Nick Richards. It uses native GTK 4/libadwaita on the GNOME 51 Flatpak runtime, requires Python 3.14 and identifies as `com.nedrichards.Skyloom`. The maintained feature boundary is below; validation evidence is in [DELIVERY_REPORT.md](DELIVERY_REPORT.md), and outstanding work is in [ROADMAP.md](ROADMAP.md).

| Area | Delivered behaviour |
| --- | --- |
| Account | Dedicated app-password login, custom HTTPS PDS, libsecret session persistence/refresh, restore and sign-out, neutral startup with delayed feedback and separate recovery. No plaintext token fallback. |
| Reading | Following and pinned feeds, cache-first switching, automatic paging with manual retry, text/facets/links/hashtags, repost/reply context, quotes, images and optional descriptions. |
| Conversations | Activate any post/quote tile; repeated activation of the current conversation preserves its page and Back stack; dedicated connected conversation rows, parent-first/oldest-sibling reading order, opened-message highlight, parent/first-reply keys, Return/Undo, branch-local incremental loading/retry, bounded gaps/deduplication and focus/scroll preservation. Feed comments open their exact URI in this view, including on other authors’ threads. Saved posts remain readable offline. |
| Reactions | Like/unlike and repost/undo, optimistic updates across mounted views, rollback on failure and guarded Undo. |
| Writing | New posts, replies and quotes; Unicode grapheme/UTF-8 limits, link/hashtag/resolved-mention facets, four JPEG/PNG attachments with required descriptions, resized metadata-free upload copies. |
| Drafts | Debounced local persistence, safe close/send, reply/quote references and attachments, Drafts list, offline writing/save/reopen, disabled offline publishing. No automatic outbox. |
| Profiles | Full biography, statistics when supplied, filters, follow/unfollow, confirmed mute/block; unified scrolling with compact identity in the toolbar; one wrapping actions/filter row, and your own profile opens from the footer account card. |
| Discovery | Full-height post/people search with initial/loading/empty/error/retry states and pagination, pinned-feed discovery, notification list/cursors/unread badge and explicit Mark seen. |
| Safety | Content visible by default with wrapping label chips, explanation/scope popovers, exact-value copying, preferences and local Show/Hide controls; optional warning cards, separate viewer mute/block handling and external reporting route. This is not the full Bluesky moderation-preference/labeler engine. |
| Offline | Thousands of archived feed posts, persisted reading windows/positions, offline cached-page replay and bounded image cache; cached post/quote reopening; cached/local images. Network operations remain explicit, and errors retain readable content. |
| Refresh | Five-minute active-window freshness, immediate stable-order arrivals, Go to top/position Undo, network-cost/connectivity/power-saver gates, suspend-aware clock, bounded retry backoff. |
| Native interface | Adaptive closable sidebar, single visible overflow menu, concise preferences with Authentication/Sign out at the bottom, consistent tile padding, one content scroller, system/light/dark/high-contrast support, large text, native image viewer and contextual shortcut help. |
| Input | Keyboard list movement/activation, pane switching, destination shortcuts, reversible top jumps/reactions, double-tap/click active destination to top and deliberate touch pull-to-refresh. |
| Packaging | Meson, original Open Loom full-colour/symbolic icons, desktop entry, GSettings, AppStream, hashed dependency sources, local x86_64 Flatpak repository and bundle. |
| Development | Isolated invented-data demo, HTTP contract tests, actual-runtime native widget tests, installed GUI smoke and reproducible local checks. |

Reporting and unsupported video open Bluesky externally. DMs, native video, account switching, post deletion, bookmarks, server drafts, feed editing, full translation support and public distribution are not delivered. There are no inert controls for these features.

Background refresh inserts arrivals above existing posts without reordering them or moving the reader. Restart restores the saved post/offset/selection and accepts a fresh head order; user input before that response preserves the live order instead. Manual refresh explicitly accepts the server's head order and goes to the top. Undo returns to the previous position while keeping refreshed data. Unchanged tiles retain identity, counters update in place and manual-refresh visible arrivals respect reduced motion.

Each pending update batch is announced once. Window activity, menus and returning
to a page do not replay its toast; Show new items and Ctrl+Shift+Home retain the
action after dismissal. Repeated offers of the same item identities reuse the
notice and update its action, while a distinct batch can announce even when its
count is unchanged. A feed refresh with no additional arrivals stays quiet.

Resizing into the narrow layout slides the sidebar out above the live content;
widening brings it back with the native spring transition. Reversing a resize
can reverse the transition, and disabled animations/reduced motion keep the
layout change immediate. Sidebar state, accessible toggles and native focus
return continue to use the same split view.

The local archive targets 10,000 posts per feed/50,000 per account, with automatic oldest/30-day cleanup and protection for saved reading windows. GTK retains a separate 250-post window. Non-overlapping history has an explicit automatically paged gap with manual retry. Offline paging uses saved real cursor pages; evicted pages require reconnection. These are cached reading records, not a complete permanent Bluesky archive.

Conversation cards in feeds, profiles, search, quotes and conversations show a
quiet position pill beside the timestamp, such as `1/6`, counting known messages
in reading order across branches. `1/6+` means
the conversation is incomplete (more context, unavailable messages or a loading
limit). Loading controls, missing-message placeholders and embedded quotes do
not count as posts. Position knowledge is shared across views and updates mounted
pills without rebuilding cards. It retains only bounded relationship metadata
for this account session and makes no extra network requests. Unknown context
can initially show `1/1+`; other independently known conversations have separate
counts, and ordinary standalone posts have no pill. Tooltips and accessible
labels explain that these are known-message counts, not a guaranteed server-wide
total. Account changes/sign-out clear this knowledge.

Card text remains selectable. A single click tolerates pointer jitter below the
desktop's GTK drag threshold and opens after the double-click interval. Deliberate
drags (even returning to their start), double-click word selection, Shift-click,
existing selections and rich-text links keep their own behaviour. Touch selection
is not cleared by the mouse jitter correction.

Read/unread notification envelopes preserve row geometry and expose read state to assistive technology. Reactions retain their filled glyph/check and gain a quiet accent and short opacity feedback. Feedback respects modern/legacy GTK reduced-motion settings, power saver and window activity; no animation loops at rest. Refresh uses one freshness/backoff deadline and resumes from activity/focus/worker events.

Post cards keep avatar/name/handle in one natural-width profile target; empty header space remains conversation navigation. Content-label buttons wrap without grid-cell focus stops. Metadata is secondary to the body, and actions share symbolic icons/counts. Pointer interaction retains the logical list cursor without a persistent selection wash; direct keyboard row focus gets an outline around the reading-width content. Tabbing into a control moves the ring to that control, and selectable text/links keep native behaviour.

New feed arrivals appear in the shared native toast queue with Go to top; no full-width bar changes the reading viewport. Posts are already in the feed; dismissal keeps navigation available through Show new items in the overflow menu and Ctrl+Shift+Home. Notifications are scoped to the current page and deferred while a dialog/popover owns interaction. Top-edge wheel/no-op keyboard/top-jump feedback uses a small damped peek; smooth/touch overscroll remains native. It does not alter the model, scroll adjustment or reading anchor, and stops on movement, unmap, close, reduced motion, inactivity or power saver.

New post uses a normal native plus button in the header, with the existing tooltip, Ctrl+N and hover/focus feedback. Post inside the composer retains the primary suggested-action styling.


The appearance chooser retains native keyboard/selection behaviour with a consistent arrow/surface border across themes. Reading-position saves update a small bookmark record; archive cleanup and the 250-post rendered window remain separate. Decoded images additionally have a byte/count budget, and offscreen list pictures release/reload their paintables while preserving card geometry.

Position Undo toasts last two seconds and dismiss when the window becomes inactive,
so returning to a reading position does not replay a stale top-jump message.
Keyboard/menu Undo remains available after dismissal; reaction toasts retain five seconds.

Reaching the top of a feed clears its pending new-post arrival notice and unseen count, regardless of the scrolling input.

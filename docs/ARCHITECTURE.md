# Architecture

Skyloom 0.1.0 is Python/GTK 4/libadwaita, installed by Meson into /app/share/skyloom and launched by /app/bin/skyloom. GTK 4.24.1, libadwaita 1.10.0 and Python 3.14.9 were inspected in GNOME 51. The protocol SDK is atproto 0.0.73; regex 2026.9.29 supplies UAX #29 grapheme segmentation. Python dependencies are version-locked, with wheel URLs and SHA-256 hashes in python-dependencies.json and requirements-hashed.lock.

## Boundaries

- `profile_header.py`: a stable-height Gtk.Stack crossfades the page title to compact avatar/name/handle as the expanded identity leaves the scroll viewport. It measures identity bounds locally within the scrolling header, avoiding stale viewport geometry during adjustment changes; mapped guards handle recycling. Bounded frame callbacks run only after layout/scroll events, and view closure disconnects handlers. Native GTK animation settings control the crossfade.

- `refresh.py`, `refresh_monitor.py`: pure freshness/backoff/resume decisions plus Gio NetworkMonitor and PowerProfileMonitor signals. A nonblocking Python timerfd on CLOCK_BOOTTIME joins the GLib main loop, expires once at the freshness/backoff deadline across suspend without waking hardware, and is removed while ineligible, editing or busy. Focus/activation and coalesced worker completions re-evaluate the deadline; unrelated completions do not postpone it. Activation/network/power changes recheck immediately; fallback uses a one-shot, second-coalesced GLib timer for the same delay. Only active, signed-in, nonbusy eligible feed/notification pages refresh. Dialogs and text editing pause it. Refresh timing belongs to the active session; real cursors and reading windows are persisted independently. Older bare-list cache records remain readable.
- `keyboard.py`, `interactions.py`, `list_interaction.py`, `list_state.py`: one shortcut registry drives GActions, context dispatch and native Adw.ShortcutsDialog help. The native SingleSelection cursor excludes loading controls. List focus is explicitly transferred before cursor movement. Held actions, popup/dialog/editor exclusions and hardware key release identity prevent accidental repeat mutations/navigation. Stable post keys plus pixel offsets restore reading positions after jumps or feed insertion. Touch-only pull-refresh uses a deliberate vertical threshold; active-destination double press offers top/Undo. Undo callbacks validate account generation, view liveness and reaction state.

- `pagination.py`: event-driven autoload two viewports ahead with one outstanding page, cursor-attempt guards, no-progress suppression, terminal-page detection and explicit retry after errors. `FeedView` flattens content and a footer model into one virtualised ListView directly inside a full-width ScrolledWindow. Per-row clamps retain the reading width; frame-aligned checks wait for new layout before requesting another page.
- `domain.py`: frozen Author, Post, Media, Notice and Page DTOs; defensive lexicon/union mapping; timezone-aware formatters; bounded deduplicating Pager. Unknown count fields remain unknown rather than inventing statistics.
- `richtext.py`: extended grapheme and byte constraints, escaped Pango markup, boundary-checked incoming UTF-8 facets, outgoing links/hashtags and DID-resolved mentions.
- `service.py`: replaceable account/service adapter over the actual async SDK. App-password sign-in, restore, refresh callbacks and sign-out; feeds, threads, reactions, writing, profiles, follows, moderation, search and notifications. API operations are serialised to avoid refresh/mutation races. Requests time out; rate limits establish a shared Retry-After cooldown. Mutations are never automatically retried.
- `credentials.py`: libsecret only. Session create/import/refresh writes are awaited. Failed refresh persistence must be retried before another authenticated operation. Keyring operations are cancellable, bounded in time, and cancelled on shutdown. The app password is never persisted. The single-account secret is keyed by application; account data is keyed by DID.
- `storage.py`: per-account SHA-256-named SQLite stores with explicit transaction/connection lifetime and restrictive file modes. Indexed post/page archives retain up to 10,000 posts per feed and 50,000 per account; 12 saved reading windows retain up to 250 posts each. Count/30-day age cleanup protects saved windows. Identity allows offline session restoration; normal auth errors still require re-authentication. Draft records retain reply/quote strong references and processed image paths. Sign-out clears account state and image copies. Corruption is reported and originals retained; no silent destructive recovery.
- `media.py`: four concurrent fetches, HTTPS Bluesky CDN allowlist, 8 MB download cap, 30 megapixel decode limit, 32-entry immutable texture cache plus an account-private disk cache of up to 128 MiB / 2,048 encoded images. Disk IO, decode, immutable texture construction and eviction run off the GUI thread; concurrent identical image consumers share work with last-consumer cancellation, and account generations isolate results. Rows defer uncached media until near the viewport, cancel it on recycling, and assign cached textures directly; least-recently-used files are evicted. Startup catalogs allow offline rendering before any download. Corrupt entries are discarded, online loading can recover, and Preferences reports storage errors. Sign-out invalidates late downloads before deleting the account cache. Platform Glycin/GdkPixbuf decoder isolation remains enabled. Attachments use supported JPEG/PNG input, bounded resize without upscaling, metadata-free pixel reconstruction and at-most-1-MB upload copies.
- `worker.py`: dedicated asyncio thread with a concrete platform EventLoop and explicit empty base Context; at most 32 outstanding jobs (local saturation has a distinct busy message, not a server-rate-limit message); GLib.idle_add completes on the main thread. Cancellation, page liveness and generation guards prevent abandoned work from mutating a new account view. Shutdown cancels work, closes the SDK HTTP client and joins the worker.
- `application.py`, `window.py`, `widgets.py`, `composer.py`: GNOME application lifecycle, GActions, adaptive OverlaySplitView/NavigationView, virtualised ListView rows and shared presentation. The composer has debounced serial draft writes, guarded close/send, native file selection and failure-preserving drafts. Post and profile text are treated as untrusted; markup is escaped or disabled.
- `demo.py`: explicitly selected offline adapter sharing DTOs and widgets. It cannot authenticate or publish to the service. Demo preferences are memory-only; draft storage uses an isolated temporary directory, removed on shutdown. `smoke.py` is permitted only with --demo and captures rendered fixture windows after frame/allocation checks.

The controller remains intentionally straightforward: one window module owns navigation and page callbacks. There is no generic repository framework, web view, analytics backend or polling daemon.

## One content scrolling surface

Profile intro/biography/actions/filter and search fields are native Gtk.ListHeader content in the first Gtk.FlattenListModel section. The ListView remains directly inside its sole ScrolledWindow, retaining virtualisation and unchanged post/footer indices. The footer section supplies a header even with no posts. An explicit header owner handles GTK's new-bind-before-old-unbind ordering without double parenting or losing controls. Search keeps one view and entry across queries/mode changes; focused fields survive rebinding, and Ctrl+K remaps the header before focusing the entry.

All timeline surfaces share completion-time, delta-aware anchor handling in
`FeedView.set_items`: pure appends and layout-stable counter/read patches need no
correction, active momentum suppresses corrections, and static prefix changes or
row removals preserve the visible key/offset without an initial item-based jump.
Focused rows transfer to the native list before removal. Conversations opt out
and retain their specialised loader/projection policy. Profile and Search post
paging use `Pager.appended` with the current anchor; people and notifications
use the analogous bounded `RecordPager` path, retaining the actual request cursor
when only part of a page fits. Search posts use shared post recycling. Native
slots retain post shells lazily from first post bind, or separate reusable
people/notification row and avatar shells, with binding-specific cleanup.


GTK scroll_to(0) targets the first post rather than its section header, so initial/reset/top paths restore adjustment zero after allocation. Scroll snapshots distinguish a visible header offset from a post URI/offset, allowing top/Undo and Back to preserve introductory content too. Unmapped headers are excluded from geometry probes because GTK can return cached bounds. Expanded biography text is complete and profile controls wrap at narrow widths. Home, conversations, notifications and Drafts already use one primary content surface. The image viewer now puts the image, full description and copy control in one scroller.

Verified upstream contracts: [ListView header factory](https://docs.gtk.org/gtk4/method.ListView.set_header_factory.html), [ListHeader lifecycle/properties](https://docs.gtk.org/gtk4/class.ListHeader.html) and [virtual list scrolling requirements](https://docs.gtk.org/gtk4/section-list-widget.html).

## Safety and scope

Labelled posts, quoted posts, media and profile biographies are visible by default with wrapping native menu-button chips. Each lazily created popover shows a standard global meaning when known, the exact selectable/copyable label value and its post/author/profile scope. Custom definitions and labeller identities are not supplied by the current immutable model, so they are not inferred. Three inline chips plus an all-labels count bound inline widget growth; popover details scroll independently only inside the popup. The warn-labelled-content GSettings preference enables a clear hidden-content card and lazy first disclosure; a native 150 ms revealer respects animation preferences. Session-only Show/Hide choices synchronize mounted copies of the same key and persist during row recycling and mutations, with independent post/quote/profile keys and a 1,024-choice bound. Changing the preference updates current posts and profiles without a network reload. Explicit viewer mutes/blocks remain separate. This is not a full Bluesky moderation-preference/labeler engine. Standard meanings follow the [Bluesky moderation documentation](https://bsky.network/docs/advanced-guides/moderation/); this presentation does not infer labeller-specific severity or change filtering policy. Reports and unsupported video use explicit external Bluesky routes. No unsupported DM, video-upload controls are displayed.

Offline server actions are read-only and keep a Retry route; new/reply/quote drafts can still be written, saved and reopened. Opening a retained post shows its saved content immediately, then loads conversation context when online. A server failure does not misclassify the whole application as offline. Feed switches load their own saved page before requesting the network. Empty draft records are deleted, and legacy empty records cannot crowd saved drafts out of the list. Notification Mark seen updates visible rows after server success and fetches the actual remaining unread count. Failed optimistic reactions restore the immutable snapshot across views. Drafts survive send failures; a connection failure after a server-side post can be ambiguous, so the UI asks the user to check their profile before retrying. Uploads cannot be rolled back as a transaction; a failed later step may leave an unreferenced server blob, never a fabricated success.

Draft and cache files are local application data, not encrypted independently of the filesystem. Prepared image copies are retained until sign-out; abandoned copies are a known cleanup improvement. Auto-downloading arbitrary remote media is deliberately unsupported. English is the delivered UI; translation catalogues and full internationalisation remain future work.

## Verified upstream surfaces

The implementation was checked against the installed SDK's generated Params/Data/Record types and current primary documentation:

- [SDK client and async signatures](https://atproto.blue/atproto_client/client/)
- [Session import/export and refresh callbacks](https://atproto.blue/guides/authentication/)
- [Posting, facets and media](https://atproto.blue/guides/posting/)
- [GTK FileDialog](https://docs.gtk.org/gtk4/class.FileDialog.html)
- [Native adaptive navigation](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/class.OverlaySplitView.html)
- [Flatpak manifests](https://docs.flatpak.org/en/latest/manifests.html)
- [Gio NetworkMonitor, including the Flatpak implementation](https://docs.gtk.org/gio/iface.NetworkMonitor.html)
- [Gio PowerProfileMonitor](https://docs.gtk.org/gio/iface.PowerProfileMonitor.html)
- [Python timerfd and CLOCK_BOOTTIME](https://docs.python.org/3.14/library/os.html#timer-file-descriptors)
- [Adwaita native shortcut help](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/class.ShortcutsDialog.html)

## Refresh and download policy

Connectivity synchronisation updates registered reaction controls in place; it does not emit whole-list replacement notifications. Unchanged connection and loading-policy state does not requeue paging checks. Feed-option metadata preserves the selected feed under frozen notifications; a removed feed falls back once. Post-row cancellation includes avatar jobs, and queued media rechecks memory cache after obtaining a download slot.

`feed_switcher.py` presents the existing Gtk.DropDown model and selection as grouped native buttons inside the Home header. Its own minimum request permits a compact dropdown; actual title allocation determines full strip, horizontal scrolling or dropdown, without adding a header row. Full feed names determine strip fit. Selection uses the existing dropdown signal and immutable feed IDs, so switching, caching, metadata recovery and reading checkpoints retain their existing path. One bounded frame callback coalesces allocation/model changes and reveals the selected button. Adaptation is automatic; no manual collapse controls or their width reservation remain. GTK crossfades last 280 ms, and arrow scrolling 160 ms, subject to local motion policy. Hidden stack pages keep native focus/accessibility handling; focus transfers when a focused page collapses. Unmapping cancels pending callbacks and scrolling, and unrealising disconnects model/picker signals. The title label ellipsises with a full-name tooltip while popup rows retain complete names.

Home actions are allocated inside `FeedSwitcher` so visibility cannot change its available-width budget. Full measured feed names plus both selector arrow widths take priority. New post then Refresh require twice their measured width plus spacing from the remaining budget, leaving an extra action-width allowance. Hidden children retain measurable sizes; their presence never changes the outer minimum width. Focus returns to the selector if an action disappears. Menu actions and shortcuts remain available.

The visible Following/pinned feed or notifications list becomes stale after five minutes. Feed head responses are reconciled immediately: background arrivals prepend while the relative order of existing rows stays stable. Known rows receive fresh content/counters; omission from a head page is not deletion. Restart's first eligible head refresh and explicit manual refresh accept the server's head order. Restart restores the visible post; manual refresh jumps to the top. Any real input before startup refresh disables the automatic reorder. Manual refresh remains an explicit reorder even after interaction.

`feed_coordination.py` owns transient startup ordering, arrival counts and gap traversal; `reading.py` captures a post URI, logical-pixel offset, separate selection and up to eight neighbouring identities per feed. The selected pinned feed is saved per account; restart validates it against cached choices and falls back to Following if unavailable. A one-second event-driven checkpoint coalesces saves; identical snapshots do not write and only one save runs per view. Bookmark-only updates write one small row without serializing posts or rebuilding protection. Window/content changes are compared as immutable records and archived on workers; head metadata references URIs rather than duplicating payloads. Checkpoints run before page navigation, feed switching and window close while row geometry is still mapped; unmap flush and application worker-shutdown cleanup retain the final snapshots. The process can lose its last unsaved second if killed. Saved windows and head responses are separate records, so a network fetch cannot overwrite the reading place. Legacy bare-list/head caches remain readable. Storage validates account epochs inside the same per-account IO lock used by clear, so an old thread cannot recreate cleared data. Service local operations capture their owner before queueing. Blocking keyring operations retain SDK ownership until completion even across repeated cancellation; failed rotated-session persistence remains a recovery requirement. Restoration waits for allocation, clamps offsets for changed row sizes and yields to subsequent pointer/touch/wheel/keyboard input. Missing identities fall back to a saved neighbour.

A refresh with no overlap retains readable history behind an explicit gap. Real server cursors fill visible gaps automatically (up to eight page attempts per view), with a native manual fallback/error retry. Repeated cursors/no-progress stop; there is no fabricated continuity. Full windows keep the reading anchor and rewind omitted tails to real page boundaries. If bridging would evict the reader, it stops with a readable recovery message. Pagination likewise protects a reader who moves while a request is in flight. Archived pages can be replayed offline only when every referenced post remains cached; missing/evicted pages report that reconnection is required rather than returning an incomplete page with a misleading cursor.

The native feed toast says **Go to top**: its posts are already available by scrolling upward. Dismissal retains navigation through Show new items/Ctrl+Shift+Home. The title is “New posts available”: fetched head pages do not establish the total number of arrivals. Repeated arrivals retain their identities within the retained window for announcement deduplication. Go to top and manual-refresh Undo restore position only, keeping inserted posts, fresh counters and pagination state. Notification-list updates retain their separate Show transaction.

Unchanged PostObjects retain identity. Counter/viewer-reaction changes emit a model signal and patch the existing row controls; media, text, quotes and labels are not reconstructed. Content changes still rebind. Reaction callbacks read the row's current snapshot. Manual refresh suppresses automatic paging while the list layout settles, selects the first post and corrects the adjustment to zero; only newly visible arrivals then receive a 160 ms opacity-only reveal. Offscreen arrivals expire after allocation. Reduced motion, scrolling, pointer/keyboard navigation, unmapping and close clear pending reveals and restore opacity. No geometry animation is used. Automatic errors preserve data and back off at 5, 10, 20 and 30 minutes; manual Refresh explicitly overrides freshness and cost gates. Resume detection compares BOOTTIME with monotonic elapsed time and clears an old failure delay, then applies the normal eligibility/freshness checks. One CLOCK_BOOTTIME deadline replaces periodic minute checks. Ineligible or busy windows have no refresh timer; focus, activity, network and main-thread worker completions reconsider eligibility. An unchanged target/freshness deadline is retained across unrelated completions. The timerfd interval is zero, with a one-shot GLib fallback. No alarm timer or idle-window polling is used.

Metered-by-default, power saver, offline and limited connectivity pause automatic paging and uncached image downloads too. Cached/local media remains readable. Opening a viewer and manual page/refresh actions are explicit overrides. Desktop connectivity is reported as available/full/limited/metered; no Wi-Fi/mobile identity is invented. Offline changes disable publishing without preventing draft editing. New notifications never mark themselves read. Default settings enable refresh and disable automatic metered downloads; both have live preferences.

## Selected application identity

The maintainer selected and authorised the refined **Open Loom** identity. Canonical full-colour and symbolic SVGs are in `data/icons/`; Meson installs them at the matching hicolor application paths and the welcome screen resolves the installed icon by name. `design/icon-concepts/open-loom-final.png` and its seven small-size renders document final light/dark QA. Discarded directions, old comparison sheets and superseded icon screenshots have been removed. These are original editable vectors following the [GNOME icon guidance](https://developer.gnome.org/hig/guidelines/app-icons.html).


## Python and lint baseline

Python 3.14 is required by project metadata and Meson. Immutable domain and attachment models use slots, preserving dataclass replacement and nested cache serialization. Deferred annotations support recursive Post types. Worker shutdown runs inside the active loop without depending on global asyncio policies; request contexts propagate independently of the base thread context. The rule policy and runtime benchmark evidence are in LINT_POLICY.md and PYTHON_314_AUDIT.md.

## Conversation context and tile activation

`conversation.py` decodes immutable ThreadPage snapshots with parent edges, unavailable/blocked gaps and continuation anchors. Conversation retains URI-keyed relationships and a deterministic projection: parents before children, sibling branches oldest first (UTC-normalised creation time, URI tie-break; invalid/naive dates last), subtrees together. Initial ordering keys stay stable during merges; newly discovered older siblings insert in place. A shallow refresh updates records while retaining deeper loaded branches and local reaction overrides. Quotes remain embedded references, not graph edges. Cycles and duplicate URIs are bounded; retained posts are capped at 250, with at most 250 gap nodes.

`conversation_view.py` renders that projection through the shared native FeedView. Post rows retain native content/actions/labels, with connected theme-aware rails, branch breaks, parent navigation and explicit “Opened here” text plus a subtle surface. One fixed rail preserves content width at narrow sizes and large text. Missing-message rows and branch-local load/retry controls are outside the post cursor but their controls remain reachable by Tab. Busy/offline state disables network controls; loaded relationship navigation and offline drafts remain available. Parent buttons ellipsise long names while retaining the full accessible relationship.

`thread_context.py` retains at most 2,000 URI/parent/root/time/reply-count records
per account session, without post text, authors, media or persistence. Unioned
parent/root references connect known fragments; iterative parent-first traversal
keeps oldest sibling branches together, independently of feed display order.
Missing parent/root references, unmatched reply counts, explicit conversation
frontiers/gaps/unavailable/limited state and malformed cycles mark context as
incomplete in tooltips/accessibility; visible pills have no `+` suffix.
Pills require at least two known connected posts, even when an isolated post
has replies, missing references or has been opened as a conversation.
`PostPositions` shares this knowledge between native post cards across feeds,
profiles, search, embedded quotes and conversations, using weak row registrations.
Quotes receive their own position and never become edges of the containing post.
Mounted labels update in place without card rebinds, media restarts or focus stops.
Sign-out/account shell replacement resets the owner.
Tooltips/accessibility describe known messages, not a guaranteed server total.

`thread_prefetch.py` owns a 32-entry session snapshot cache (120-second freshness),
a 128-root attempt ledger (300-second cooldown) and six Home requests per rolling
minute. Home viewport events debounce for 350 ms; only visible posts with reply
evidence qualify, complete known groups are skipped, and a single shared request
slot yields to foreground reads. Results enrich PostPositions without changing
the feed model. Unmapping/closure/ineligibility cancels owned work; request-scope
account/generation guards reject stale completions. Automatic failure does not
retry. Conversation initial loading reuses a fresh snapshot containing its exact
anchor; explicit refresh always requests the service. Branch/ancestor fragments
do not replace full initial snapshots. Conversation loading examines native rows
one viewport beyond visibility and shares a three-request speculative lookahead
budget across ancestor/reply continuations. Changing the first visible post renews
the budget; reply lookahead follows the inferred reading direction. Visible loaders
remain eligible independently of that budget. Conversations disable the generic
feed-end pager, retaining the single request slot, 250-post cap and retry controls.

Conversation status-only syncs reuse decorated posts and patch retained loader
widgets without projecting the graph. Content merges capture the current viewport
at completion, never at request start. Unchanged content before the first visible
row needs no correction; stationary insertions above it settle the current anchor
without an initial native reveal. Recent scroll input, extended by kinetic
adjustment changes within 150 ms, suppresses background viewport/focus corrections.
Expired activity cannot be restarted by programmatic adjustment changes. Explicit
navigation retains its reveal behaviour; new input cancels pending restoration.
Queued automatic checks recheck positioning readiness before requesting data.

Adversarial review tightened cache ownership: immutable snapshots retain the actual
request anchor, original network timestamp and an indexed set of fetched-subtree
URIs. Ancestors included only for context do not qualify for cache reuse, so opening
them fetches their missing sibling replies. Cache hits merge under the original
response anchor while keeping the user's selected post as the UI anchor, and never
renew freshness. Local reaction revisions patch existing snapshots and reconcile
older in-flight responses; requests begun after an acknowledged change can accept
new server reaction state. Pending reactions remain protected. The revision ledger
stores only four reaction fields per URI and is bounded to 2,000 records.

Home requests the exact visible post while deduplicating attempts by conversation
root. Policy/worker reconsideration resumes blocked work without resetting a
viewport debounce. Scoped foreground reads and mutations cancel the shared
speculative request; request-slot identity rejects late results. Controllers recover
when global cancellation removes their slot, and sign-out clears snapshots and
reaction state. PostPositions updates only mounted pills whose projected position
actually changed, rather than setting GTK/accessibility properties for every row.

Long top jumps bypass the item-position request and set the adjustment to zero
directly, correcting it after layout. They skip the top peek; nearby jumps keep
it. GTK virtualisation owns destination rows; no model items are removed or
rebuilt merely to jump. The original stable key/pixel anchor remains available
for Undo. A native 60-post fixture jumps from post 45 and asserts no intermediate
adjustment values, destination completion and exact anchor/offset restoration.

Alt+Up/Down select the loaded parent/first direct reply only in conversation list context; header buttons provide the same actions. Existing list/post commands are shared. Return to opened post appears when its row is outside the viewport and has Undo. Reactivation of the current anchor focuses its visible body without pushing a duplicate page. Merges preserve a URI/pixel viewport anchor and selection, and restore a replaced descendant control by semantic identity after allocation; busy loaders retain logical control focus and keep Enter from opening the previously selected post, without changing the reading position; errors restore their retry button, and disappearing loaders return to their parent or nearest visible message. Only actual presentation changes rebind retained rows: increased graph depth alone does not restart media work. Completion/error announcements use GTK’s polite accessible announcement API on mapped pages; actual Orca acceptance remains a human gate.

Requests still retrieve two reply levels and up to 20 ancestors through the pinned SDK’s supported getPostThread route. Further replies are anchored at branch posts with parentHeight=0; earlier ancestors use depth=0. There is no invented API cursor. One request per page, generation/liveness guards, cancellation, failed-frontier state and fetched-anchor deduplication prevent concurrent or repeated automatic traversal. Eligible visible continuations autoload with manual fallback. The fallback Retry captures the exact failed request; success clears that retry and resumes normal branch paging, including after an offline cached start. Server-selected/omitted siblings can still limit wide threads; the browser route and opening another message remain available.

Ordinary feed order is retained. Consecutive same-author posts with verified direct parent links receive a compact joined-thread treatment; unrelated/non-consecutive/cross-author posts are not grouped. Every member stays individually selectable/actionable with its own attribution and labels. Selecting **any** post, including a comment on somebody else’s thread, opens the exact selected URI in ConversationView with available ancestors/replies; feed grouping never changes the target to the thread root.

FeedView uses a native SingleSelection cursor; row click gestures open posts while footer/ancestor-control rows cannot be selected. Native single-click activation is disabled so pointer hover never moves the keyboard cursor. PostRow has a standard GTK activation signal for quoted cards, keyboard controllers and accessible activation. The body-label click gesture shares the label’s native gesture group, allowing links, drag selection and double-click word selection. A capture-phase press records existing selection/Shift state before native selection changes; pointer motion latches GTK's drag threshold, including excursions returning to the start. A plain mouse release clears only incidental sub-threshold selection. Existing selections, deliberate drags, Shift-click and touch selections stay native. Mouse text activation waits for the system double-click interval and is canceled on another click, selection, unbind or navigation; touchscreen text activation has no such delay. Buttons and menus retain their own gestures. Post content has 20-pixel inner margins; compact quoted content has 16-pixel inner margins inside its card. No extra Read/Open button is rendered. The native image viewer owns the optional browser action.

Conversation pages retain their anchor URI as navigation identity. Requesting the currently visible anchor is a no-op for the stack, loading and focus/scroll position (while revealing content if navigation overlays it). Different anchors still push distinct pages; Back restores the previous page, and reopening from the feed creates a fresh conversation. Identity is assigned before cache/network work so rapid repeated activation cannot enqueue duplicate pages.

The initial conversation positions the opened post before enabling scroll-triggered loading. Ancestor prepends and branch insertion restore reading position; shallow refresh does not discard already loaded deeper messages. Ancestor and descendant loads share a single page request, and page removal cancels it and any positioning callback. Append errors preserve all readable posts. Conversation state receives reaction updates, while each view preserves its own context labels during reconciliation.


## Navigation visibility

`navigation.py` owns the native Adw.OverlaySplitView and creates bidirectionally bound Gtk.ToggleButtons. The button's pressed state, tooltip and accessible label track actual show-sidebar state, including native overlay dismissal and resizing. The former NavigationSplitView show-content property selected the narrow pane but could not hide a wide sidebar. All content headers now expose the same actual visibility toggle; the narrow overlay also has a close toggle inside its sidebar header.

A single window-lifetime breakpoint collapses the persistent container below 720sp. Its contents are replaced on account-shell rebuild and detached on sign-out, avoiding accumulating duplicate breakpoints. Selecting a destination closes narrow navigation while preserving the user's wide-window sidebar visibility. F6 reveals a hidden sidebar, and Back dismisses a narrow overlay before popping a content page. Covered feed views are excluded from list keyboard dispatch and automatic refresh while the overlay is open. All content widgets and their models remain mounted during visibility changes. Overflow menus bind to the same show-sidebar state: the sidebar menu is visible when navigation is shown, and every content menu uses the inverse binding, including newly created pages. Hiding a menu dismisses its popover. F10 follows sidebar visibility in both wide and overlay layouts. [GObject binding flags](https://docs.gtk.org/gobject/flags.BindingFlags.html) supply immediate and inverse boolean synchronisation.

The [native OverlaySplitView contract](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/class.OverlaySplitView.html) supplies sidebar visibility, responsive collapse and touchscreen gestures. Native GTK allocation tests check wide hide/show and content expansion, narrow overlay sizing, synchronised buttons and destination/pane behaviour. The GUI smoke clicks the actual toggles at 1280 and 480 pixels, checks unchanged feed data, F6 switching and Back with a nested profile open.

Responsive transitions use `pin-sidebar` so changing `collapsed` does not hide
the sidebar immediately. `Navigation` then uses the native animated
`show-sidebar` setter. BreakpointBin temporarily unmaps its child while applying
setters, so a visibility change requested there waits for the split view's next
map; only the latest requested target is retained. A bounded three-frame handoff
allows the initial narrow allocation to finish before starting the spring, so
dense feed reflow does not consume the animation's elapsed time. Unmapping
cancels that callback. On collapse, content and the visible sidebar share a
340 ms cubic ease-out timeline. The native sidebar spring has no public timing
control. A temporary immutable `Gtk.WidgetPaintable` render of the themed sidebar
pane is therefore drawn above the native split view during resize, moving with
the same progress as the live content. The native sidebar still handles actual
visibility, focus, dismissal and gestures. The render is decorative, cannot take
input or focus, stays only in memory and is discarded at completion or cancellation.
The content's final width is allocated once; GTK allocation transforms keep its
hit testing aligned without rewrapping text on each frame. Reversal, unmapping,
content replacement and explicit visibility changes clear both the render and
the content transform. Reduced motion and disabled animations skip this path.
There is no idle animation loop. This follows the inspected libadwaita 1.10.0
[split-view implementation](https://github.com/GNOME/libadwaita/blob/1.10.0/src/adw-overlay-split-view.c)
and [breakpoint implementation](https://github.com/GNOME/libadwaita/blob/1.10.0/src/adw-breakpoint-bin.c).
GTK's disabled-animation setting is handled by the native animation. A local
reduced-motion watcher retains the native instant collapse when GTK requests
reduced motion; it connects/disconnects with realise/unrealise and does not
change global animation settings. Native frame tests require an intermediate
sidebar position during a real breakpoint resize, correct focus return, safe
reversal and immediate reduced-motion endpoints. A full-window regression also
requires visible sidebar motion while resizing a 250-post invented feed.

## Authenticated request and deletion boundaries

The production SDK request installs an asynchronous HTTPX request hook that
requires HTTPS and rejects URL credentials before network dispatch, including
each redirect hop. This also covers endpoints adopted by the SDK from session
or DID data; checking only the custom-server form is insufficient. Valid HTTPS
custom servers and redirects remain supported. The hook follows the documented
[HTTPX event contract](https://www.python-httpx.org/advanced/event-hooks/).

Viewer like/repost/follow/block URIs are untrusted. Undo, unfollow and unblock
require the signed-in DID, the action's fixed collection and a strictly valid
[record key](https://atproto.com/specs/record-key). A read from the PDS verifies
the record's URI, type and subject before deletion; `swapRecord` binds the delete
to that verified CID. This adds one read to removal actions. Missing records
remain successful no-ops; lookup failures or concurrent replacement preserve the
UI's existing rollback/retry behaviour. Mutations are never automatically retried.

Attachment preparation uses the same storage generation and account IO lock as
drafts and sign-out cleanup. Cleanup waits for a running copy and removes it;
queued work with a retired generation does nothing. File-picker and preparation
callbacks also check composer/account liveness before updating the draft.

## Storage locations and retention

Inside the Flatpak, `$XDG_DATA_HOME/skyloom` holds DID-hashed SQLite databases and account image-upload copies. On the host these normally appear under `~/.var/app/com.nedrichards.Skyloom/data/skyloom/`. SQLite tables archive every fetched feed page and quoted record, indexed by feed/URI and age. The archive targets 10,000 posts per feed and 50,000 per account, plus protected saved windows; 12 windows hold up to 250 posts with bookmark/cursor/page-boundary/gap metadata. Cleanup runs on first use, after 512 archived records or an hour of active cache work: unprotected records older than 30 days and excess oldest records are removed. There is bounded slack between sweeps; protected windows may exceed the archive budget. Page metadata is capped at 1,000 pages per feed/30 days. Deleted SQLite pages are reused rather than vacuuming on each save. Quotes are directly indexed; legacy head JSON remains compatible. No background timer wakes the app just to prune. Search, notifications, profile data and newly loaded thread branches are not separately persisted.

Encoded CDN media lives in `$XDG_CACHE_HOME/skyloom/<hashed-DID>/`, normally `~/.var/app/com.nedrichards.Skyloom/cache/skyloom/` on the host. URLs are hashed as filenames, files are mode 0600, and account directories are mode 0700. Tokens live only in the login keyring. Preferences use GSettings. Drafts are local and are never automatically posted on reconnection. Sign-out removes account databases, drafts, prepared uploads, media cache and saved session; online revocation is best effort. Unsent attachment copies are retained until sign-out, including abandoned copies.

Frozen domain objects are mapped into a Gio.ListStore and rendered by recycled native Gtk.ListView rows. SQLite JSON snapshots reconstruct the same domain objects; there is no HTML feed, server-side renderer or hidden offline outbox. Demo storage is temporary and independent of the installed account.

## Preferences and account actions

`preferences.py` owns a native PreferencesDialog with Reading, Updates, Storage and a final Authentication group. All editable controls retain their GSettings bindings; connection state stays live. Sign out is a native destructive ButtonRow at the bottom, alongside the account and app-password/keyring information. It is absent from the overflow menu and unavailable when signed out. The confirmation overlays Preferences; Cancel restores the action's focus. Successful cleanup closes Preferences; a failed cleanup preserves the account and enables retry with a toast inside the dialog. Demo mode identifies itself and offers Leave demo. Native [ButtonRow](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/class.ButtonRow.html) and [dialog presentation](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1-latest/method.Dialog.present.html) provide these controls and stacking.

## Search states

`search.py` composes search fields, a native icon/spinner/text/action panel and results inside the same FeedView/ListView scrolling surface. The former Adw.StatusPage nested in a list header had only 58 pixels of allocated height, clipping its illustration and text. Search now gives an empty header the viewport's height, accounting for native section/footer padding after allocation. It measures native minimum sizes instead of imposing fixed window dimensions. The short frame callback is event-driven, coalesced and removed on view closure; changing to results releases the minimum immediately. Large text or short windows retain normal scrolling rather than clipping content.

Initial, loading, no-results and initial-error states share that panel. Empty pages with a real cursor retain Load more, and failed searches retain Try again. Nonempty results use the existing paging footer. Clearing the entry cancels the outstanding request, invalidates stale completion callbacks and restores the prompt. Controls retain the same instances, keyboard focus and recycled-header behaviour. Native geometry regressions check resizing, readable state content, retry and transitions back to results.

## Startup presentation

`startup.py` uses the same presentation pattern inspected in Agile Rates (`octopusagile/src/ui/main_window.py`): a neutral pending view while asynchronous credentials/session restoration runs, feedback delayed by 200 ms, and a short native crossfade. There is no minimum loading duration and no delay before data requests start. The sign-in form is constructed offscreen; it becomes the initial destination only after lookup confirms no session. A saved account goes directly to the shell, and lookup errors show a separate recovery page with retry and explicit Sign in actions.

The root Gtk.Stack and loading revealer use 150 ms native crossfades, inheriting GTK's animation/reduced-motion settings. Retry restarts the pending gate, cancels any prior request/timer and rejects stale callbacks. Closing removes the timer, stops the spinner, cancels the auth request and suppresses late UI changes. The application presents its window immediately; a fast restore therefore displays the resolved page without a spinner flash, and a slow lookup remains truthful.

Real GTK tests use a separate fixture application, memory preferences and the temporary demo adapter with synthetic restore outcomes. They trace rendered states for fast/slow saved sessions, confirm the sign-in form stays unmapped while pending, exercise missing-session and error/retry/manual-sign-in routes, verify close cancellation, and check that native transitions run only when animations are enabled. They never inspect a real login keyring or claim authenticated startup acceptance.

Profile actions and the post filter share an Adw.WrapBox, using natural child widths and wrapping only when space requires it. The account card is a native button in the sidebar ToolbarView bottom bar, registered as the Profile destination; there is no duplicate Profile row. Ctrl+4, F6 focus routing, repeat navigation and active-destination double-tap/top use that same destination. Ellipsised account name/handle labels retain a full accessible identity.

## Performance evidence

[PERFORMANCE.md](PERFORMANCE.md) documents repeatable installed native frame/presentation, CPU, memory and allocation measurements, their scope and remaining frame-budget misses. Factories retain their clamp wrappers, post headers, selectable body labels, action bars and input controllers across bindings, and use native separators; post menus are created on opening. Key-indexed model entries patch reaction controls without repeated list scans or body/media reconstruction.

Notification read-state updates use the same model changed signal and a declared row updater. A fixed-size envelope fades without changing the subtitle or row geometry; the native accessible description announces read/unread state once. Item/row identity and focus remain. Other notification content changes still rebind.

`motion.py` owns brief native opacity feedback for mapped reaction controls and unread markers. It observes both gtk-enable-animations and gtk-interface-reduced-motion, finishes feedback for power saver/inactivity/unmapping, and removes completed animations. Selected reactions retain a theme-aware accent and their existing filled glyph/check and accessible labels. Count-only changes and pending-to-confirmed acknowledgements do not replay feedback. Nothing loops at rest. Queued viewport media and automatic paging resume on activation instead of polling a background window.

## Card targets and focus

`PostRow` uses one START-aligned avatar/identity button in an expanding header slot, leaving unused space to the conversation target. The profile control has a stable per-post focus key so conversation rebuilds can restore it. Names remain primary, while handles/timestamps/context use caption styling. Action buttons retain their icon and count widgets during updates; bundled outline/filled symbolic hearts avoid an unavailable runtime icon and preserve a non-colour selected-state cue.

`LabelledContent` uses Adw.WrapBox rather than Gtk.FlowBox: children have natural-width targets, wrap at narrow widths, and have no focusable empty grid cells. Native button/popup targets, focus return, default content visibility and all label explanations are unchanged.

The shared content list retains its native selection and accessible keyboard cursor, but selected/hovered rows do not paint a full-card background. [GTK propagates `:focus-visible` to ancestors](https://docs.gtk.org/gtk4/css-overview.html), so the card outline requires both `:focus` and `:focus-visible` on the native row and is drawn on its clamped child. A focused child button or selectable label therefore does not outline the entire post. Quoted tiles use the same direct-focus rule. No global input-mode flag, forced focus clearing or pointer focus suppression is introduced; GTK continues to coordinate keyboard, pointer and assistive-technology focus.

## Upper-edge and update feedback

`list_feedback.py` adapts Brooklet Linux's upper-edge treatment to the shared native lists. `TopPeek` wraps the existing ScrolledWindow in one Adw.Bin and clips/translates its snapshot for a 360 ms damped pull-down/return. The zero-offset path draws its child directly. It never changes list allocation, row models or the scroll adjustment. Wheel signals proceed to GTK, and coalesced idle feedback checks the resulting top edge; smooth and touch scrolling retain native overscroll. Repeated wheel notches do not restart an active animation. No-op Up/Home/Page Up and top navigation share feedback. Movement, unmapping, closure and both motion preferences stop it; window activity/power policy uses the existing motion gate.

`UpdateNotice` uses the window's existing Adw.ToastOverlay queue with a plain-text title, Go to top for feeds (Show for notifications) and a five-second timeout. It does not reserve vertical space or apply scroll compensation. Closing the notice preserves its navigation/show callback; the current-view Show new items action/menu and Ctrl+Shift+Home remain available without fetching again. Replacement/dismissal/close invalidate old toast callbacks. Notices hide when their page loses interaction or a dialog/popover opens. Each batch keeps its announced state across those interruptions; returning does not replay it. An offer carries the batch item identities as a revision, so repeated results keep the current toast and latest callback, while a distinct batch can announce with the same count. Feed refreshes with no additional arrivals do not re-offer accumulated unseen posts. Focus/dialog events only reconsider pending notice presentation; they do not start network work. Feed insertion preserves the reading anchor; the notice navigates without refetching. Undo never rolls feed data back.


## Refactored operation ownership

`request_scope.py` guards request-slot identity, account/generation and page liveness before dispatching success or failure. Popping a page retires its scope immediately, including its transition. Read replacement cancels the old future; mutation presentation guards never imply server rollback/retry. `records.py` provides bounded cursor/deduplication bookkeeping for people and notifications, while specialised feed and conversation models retain their ordering semantics. The production monitor consumes the same refresh decision as commands.

Keyed list reconciliation owns presentation invalidation and the post-object index together. One Undo token belongs to its toast; an older toast cannot run a newer action. All shared lists interrupt deferred positioning on actual input, including profile/search headers. GTK distinguishes logical focus within a toplevel from global input focus; quoted-card routing and controller assertions use [Widget.is_focus](https://docs.gtk.org/gtk4/method.Widget.is_focus.html), with physical input acceptance remaining separate.

Decoded media has a 48 MiB/32-entry LRU plus weak native-consumer accounting. List media releases its paintable outside a bounded viewport margin and on unmap, without changing its 220-pixel geometry; returning can use the encoded/decoded caches. Callback epochs and completed-future cleanup prevent stale reinstalls and hidden texture retention. Pixel accounting is an estimate, not renderer-memory or battery measurement.

The appearance chooser uses the documented ComboRow/Popover CSS nodes. Its contents and arrow have matching theme border widths, with only an outer shadow on contents; the override is local to the chooser. GTK documents the arrow's custom overlap with the contents border/shadow in [Popover CSS nodes](https://docs.gtk.org/gtk4/class.Popover.html#css-nodes).

## Momentum scrolling review

[SCROLLING_REVIEW.md](SCROLLING_REVIEW.md) records current row-construction and geometry-scan costs. Healthy automatic paging hides its manual control; errors, cursor stalls and policy pauses preserve recovery. Failed images retain their reserved 220-pixel tile and explicit viewer action to avoid asynchronous row collapse. The maintainer reports improved scrolling, with remaining visual disturbance during new-item insertion in long conversations; see the roadmap.

## Reusable post cells

The shared factory creates a PostRow shell in setup and retains it on each native
ListItem until teardown. Bind supplies current immutable data; unbind disconnects
the model signal, cancels requests and releases textures, retires label gates,
clears selection/delayed activation/popovers and drops the previous post. The
native item, Clamp, header, body label, action controls and event controllers
survive. Home, profiles, search and conversation post rows use this lifecycle.
Non-post rows keep their specialised renderers. Native list buffering and the
250-post reading-window limit are unchanged.

Callbacks on retained controls read the current binding. Rebinding resets count,
reaction glyph, sensitivity, accessible name, focus keys, context and conversation
classes. A binding serial and per-image callback epochs reject retired image
results. Labelled/muted/blocked transitions detach old content and preserve lazy
disclosure; cancelled gates leave the window registry. One compact quoted cell
is retained per post cell, with the same binding cleanup. Avatars and up to four media tiles are also retained per cell. Their binding
handlers, current data and texture consumers are retired on recycling; callback
epochs protect the reused native widgets. Label disclosures, external cards and
branch controls remain item-specific. First-view native buffer size is unchanged.

The lifecycle follows [Gtk.SignalListItemFactory](https://docs.gtk.org/gtk4/class.SignalListItemFactory.html).


## Measured layout and allocation costs

Body labels use an eight-character width request with native WORD_CHAR wrapping.
The former one-character request made GTK shape hundreds of narrow lines during
ListView cross-axis measurement. The larger hint remains below the existing row
control minimum in the tested narrow/large-text cases; it does not impose a fixed
row height or restrict displayed text. Latin, CJK, Arabic and unbroken URL tests
compare row minima, allocated-width height requests and native selection.
[GTK documents the width request separately from wrapping](https://docs.gtk.org/gtk4/method.Label.set_width_chars.html).

Text, attachment-container and action-bar parent chains survive ordinary row
bindings. Media slots retain their Picture/button/description widgets and clear
hidden descriptions, paintables and current media; avatar binding handlers are
disconnected before reuse. Disclosure transitions reparent content only when its
owner changes. Warning-only controls are lazy until content is first hidden.
Explicit action/menu-item CSS classes replace ancestor-dependent action styling;
native geometry regressions compare the original and replacement declarations.

Reconciliation snapshots model entries once and maintains that snapshot alongside
splices. Identical immutable posts bypass tuple-building equality and unnecessary
replacement DTOs. ThreadContext retains unchanged KnownMessage records while
preserving LRU promotion and changed-metadata projection. Plain unfaceted markup
escapes directly; UTF-8 byte/facet processing remains on the faceted path.
[PERFORMANCE.md](PERFORMANCE.md) records measured scopes and rejected comparisons.

# Code guide

Start in `src/skyloom/`. The application uses native GTK 4/libadwaita widgets;
`demo.py` supplies an offline service with invented data.

| Area | Entry points |
| --- | --- |
| Application and navigation | `application.py`, `window.py`, `navigation.py` |
| Shared lists and post cells | `widgets.py`, `list_state.py`, `list_interaction.py` |
| Conversations | `conversation.py`, `conversation_view.py`, `thread_context.py`, `thread_prefetch.py` |
| Feed loading and reading position | `pagination.py`, `feed_coordination.py`, `reading.py` |
| Keyboard and gestures | `keyboard.py`, `interactions.py` |
| Immutable records and text | `domain.py`, `richtext.py` |
| AT Protocol and authentication | `service.py`, `sdk.py`, `network.py`, `credentials.py` |
| Profile editing and people lists | `profile_service.py`, `profile_editor.py`, `people_view.py` |
| Private bookmarks | `bookmark_service.py`, `bookmark_view.py` |
| Reply and quote controls | `thread_service.py`, `thread_controls.py` |
| Video playback and preparation/upload | `video_player.py`, `video_stream.py`, `video_upload.py` |
| Background work | `worker.py`, `request_scope.py` |
| Drafts and local data | `composer.py`, `storage.py` |
| Images | `media.py` |
| Refresh and connection policy | `refresh.py`, `refresh_monitor.py` |

GTK runs on the main thread. The worker owns the asyncio loop and sends
completions back through GLib. When tracing a stale result, follow its request
scope, page lifetime and account generation from submission to completion.

`sdk.py` uses atproto's public model serializer, including its unknown-record
fallback, and the 0.0.74 typed page-item interface. Adapters convert one fetched
page into immutable app records; native pagers retain responsibility for bounded
windows, reading positions, repeated cursors and request cancellation. Notification
mapping reads typed fields directly and avoids serialising unused post records.

For scrolling issues, start with the shared list and reading-position code;
conversations also have their own projection and loader handling. Use the
[profiling guide](PERFORMANCE.md) for measurements.

Own and other profiles share one adaptive identity/actions row. Actions sit beside
the name and handle when space permits and wrap within the header on narrow pages.

`confirmed.py` retains only successful writes for two minutes, scoped to the
exact signed-in session object and bounded to 2,000 records. Profile and
relationship fields, reactions and notification cutoffs have independent expiry;
reads never renew them. Service reads reconcile these facts across profiles,
feeds, search, people, notifications, nested quotes and cached content. Mutations
still validate the exact supplied record URI and ownership before deleting it.
Account replacement or sign-out drops these in-memory confirmations.

Profile edits return the submitted name/description and prepared local images
without a dependent AppView read. Immutable author flags distinguish trusted
prepared images from remote URLs; API mapping cannot supply those flags. The
current profile also retains its prepared banner across view replacement.

A successful publish retains its returned URI/CID and submitted text, facets,
media and reply/quote references until indexing catches up. Missing posts are
added only to the Following head, the matching author's compatible profile head,
and threads containing their parent. Indexed records win; tail pages and custom
feeds do not receive invented membership. Deleting a post removes its pending
publication. Draft cleanup failures cannot turn successful publishing into an
invitation to retry.

Notification reads apply the confirmed seen timestamp only to older records.
Unread-count requests pass the SDK's explicit `seen_at` cutoff, allowing newer
notifications to remain unread. No mutation is automatically retried.

## Storage locations and retention

Account databases and prepared uploads live in `$XDG_DATA_HOME/skyloom`;
encoded images live in `$XDG_CACHE_HOME/skyloom`. Under Flatpak these normally
resolve beneath `~/.var/app/com.nedrichards.Skyloom/data/` and `cache/`.
Tokens live in the login keyring; preferences use GSettings.

Deleted-post tombstones are account-local and prevent stale cached/network
responses restoring deleted content. Bookmarks use Bluesky's private service,
separate from the local feed reading-position bookmarks. Thread/post gate writes
preserve unrelated fields and compare record versions; separate reply and quote
saves make partial failures explicit.

Video playback uses GStreamer URI decoding through a `Gtk.MediaStream` and
`Gtk.Video` controls. Only an explicit play action creates a player; closing it
or changing accounts releases the pipeline. The Flatpak audio socket enables sound.
Video preparation runs under the account storage lease on a worker, validates
MP4/H.264/AAC, strips metadata without re-encoding, and retains private copies
until sign-out. Upload streams to the fixed Bluesky video service using scoped,
short-lived service authorisation and bounded processing polls. Uploads and post
creation are never automatically retried.

See `storage.py` and `media.py` for retention limits and cleanup. These are local
application files, not separately encrypted backups. Use temporary demo storage
when debugging or sharing a reproduction.

Feed image previews reserve height from immutable `Media` dimensions supplied by
the image embed's optional `aspectRatio`. Native height-for-width measurement is
bounded to 160–560 logical pixels, with a 4:3 fallback for older records. GTK
centres any remaining crop using `ContentFit.COVER`; image arrival/eviction and
download-policy placeholders do not change the reserved rectangle. This uses
constant arithmetic during layout, with no pixel/subject analysis, decode or
network work added to scrolling. Dimension fields survive cached post round trips.

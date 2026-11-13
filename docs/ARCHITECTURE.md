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
| AT Protocol and authentication | `service.py`, `network.py`, `credentials.py` |
| Background work | `worker.py`, `request_scope.py` |
| Drafts and local data | `composer.py`, `storage.py` |
| Images | `media.py` |
| Refresh and connection policy | `refresh.py`, `refresh_monitor.py` |

GTK runs on the main thread. The worker owns the asyncio loop and sends
completions back through GLib. When tracing a stale result, follow its request
scope, page lifetime and account generation from submission to completion.

For scrolling issues, start with the shared list and reading-position code;
conversations also have their own projection and loader handling. Use the
[profiling guide](PERFORMANCE.md) for measurements.

## Storage locations and retention

Account databases and prepared uploads live in `$XDG_DATA_HOME/skyloom`;
encoded images live in `$XDG_CACHE_HOME/skyloom`. Under Flatpak these normally
resolve beneath `~/.var/app/com.nedrichards.Skyloom/data/` and `cache/`.
Tokens live in the login keyring; preferences use GSettings.

See `storage.py` and `media.py` for retention limits and cleanup. These are local
application files, not separately encrypted backups. Use temporary demo storage
when debugging or sharing a reproduction.

# AT Protocol / Bluesky API implementation map

This maps implemented routes in `service.py` using the pinned atproto SDK. Verify installed generated types and current official docs when changing an endpoint. Future features live in [ROADMAP.md](ROADMAP.md).

Feature adapters also live in `profile_service.py`, `bookmark_service.py`,
`thread_service.py` and `video_upload.py`. The shared SDK boundary uses public
serialization and typed page-item access from atproto 0.0.74.

| User feature | Relevant lexicon / SDK surface | Requirements and pitfalls |
| --- | --- | --- |
| Session creation | `com.atproto.server.createSession` through `AsyncClient.login` | Login with dedicated app password; never use main password. SDK follows PDS discovery. Rate-limited: store and restore sessions. |
| Session refresh | SDK automatic refresh / `com.atproto.server.refreshSession` | SDK session change callback must persist refreshed session in libsecret. |
| Following feed | `app.bsky.feed.getTimeline` or `AsyncClient.get_timeline` | Authenticated, paginated cursor, handle repost/reply metadata. |
| Custom feed | `app.bsky.feed.getFeed` | Uses feed `at://` URI and cursor. Pin/feed preference lookup separately. |
| User-selected feeds | `app.bsky.actor.getPreferences` | Parse feed-view preferences, pinned/saved feed URIs; preserve server preference semantics. |
| Single post/thread | `app.bsky.feed.getPostThread` | Thread union models include blocked/unavailable/deleted, not only full post views. Stable getPostThread has depth/parentHeight but no cursor: fetch ancestor and terminal-reply anchors incrementally; bound and deduplicate the merged view. |
| Author profile | `app.bsky.actor.getProfile` | Accept handles/DIDs; custom handles; viewer state (following/muted/blocked). |
| Profile editing | `com.atproto.repo.getRecord`, `putRecord`, `createRecord`, `uploadBlob` | Own literal `app.bsky.actor.profile/self`; preserve unknown fields, compare CID and bind to the current session. Strip image metadata. |
| Followers/following | `app.bsky.graph.getFollowers`, `getFollows` | One cursor page per request, bounded native people list and stale-page/account guards. |
| Author posts/replies | `app.bsky.feed.getAuthorFeed` | Cursor + author feed filter; gracefully hide unsupported content. |
| Like / unlike | `app.bsky.feed.like` record creation / high-level `client.like`; `com.atproto.repo.deleteRecord` or high-level unlike | Need post `(uri,cid)` for like. Deleting a like requires own created like record URI, not target post URI. |
| Repost / undo | `app.bsky.feed.repost` record / SDK repost helpers | Undo deletes own repost URI from `viewer.repost`. |
| Create post | `app.bsky.feed.post` and SDK `send_post` | Correct facets, language, embeds, client-side 300 graphemes and 3000 bytes; submit once; created result URI/CID. |
| Delete post | `com.atproto.repo.getRecord`, `deleteRecord` | Confirm; validate ownership, collection and displayed CID; delete with `swapRecord`. Persistent tombstones reconcile stale caches and responses. |
| Private bookmarks | `app.bsky.bookmark.createBookmark`, `deleteBookmark`, `getBookmarks` | Save URI/CID; removal needs URI. Preserve removable unavailable entries and reconcile indexing lag. |
| Reply and quote controls | `app.bsky.feed.threadgate`, `postgate` repository records | Own matching post key; guard existing writes by CID and use fixed-key creation when absent. Preserve unknown rules, hidden replies and detached quotes. |
| Reply | `app.bsky.feed.post` with reply ref | Need `root` AND immediate `parent` strong references; don't treat every reply as top-level. |
| Quote | `app.bsky.embed.record` in post embed | Quoted URI/CID plus text; not equivalent to repost record. |
| Image upload | `com.atproto.repo.uploadBlob` / `client.upload_blob` | Use valid MIME, size cap and image thumbnails; insert `app.bsky.embed.images`, each alt text; verify current upload limits. |
| Video playback | `app.bsky.embed.video#view` playlist | Explicit native HLS playback via GStreamer and GTK controls; no session tokens sent to media URLs and no feed autoplay. |
| Video upload | `com.atproto.server.getServiceAuth`, `app.bsky.video.getUploadLimits`, `uploadVideo`, `getJobStatus` | Use scoped, short-lived service auth; stream once, bound processing polls, verify job owner/blob and preserve failed drafts. Prepare described MP4/H.264/AAC copies within 10 minutes/300 MB. |
| Rich text | `app.bsky.richtext.facet` + SDK text builder/rich text utilities | Byte offsets measured in UTF-8 bytes, not Python Unicode indexes; mentions require DID resolution. |
| Link preview | `app.bsky.embed.external` rendering | Render incoming records safely; no arbitrary URL metadata fetch or outgoing link-card creation. |
| Search posts | `app.bsky.feed.searchPosts` | Search results not same shape as chronological feed; guard unauth and rate limits. |
| Search users | `app.bsky.actor.searchActors` | Explicit query submission; accept custom handles; separate user vs post results. |
| Notifications | `app.bsky.notification.listNotifications`, `getUnreadCount`, `updateSeen` | Correct read/seen semantics, cursor and reason types. Avoid per-second polling. |
| Follow/unfollow | `app.bsky.graph.follow` record / deleteRecord | Follow state stores record URI; follow DID, not display handle as immutable identity. |
| Mute/unmute | `app.bsky.graph.muteActor`, `unmuteActor` | Mute is a non-public action; UI state and cache should reflect it. |
| Block/unblock | `app.bsky.graph.block` record / deleteRecord | Blocks stored as records; own block URI needed for removal; confirm when appropriate. |
| Content labels | Incoming labels and viewer state | Visible label notices, optional local disclosure, separate mute/block handling; no full labeler preference engine. |
| Report | External Bluesky route | Opens Bluesky for reporting; no in-app report submission claim. |

## Common mistakes to prevent

- **Record URI vs CID vs handle vs DID.** All four are distinct. Account identity anchored in DID; mutable handle displayed to user. Each post has an AT URI and CID. Own like/repost/follow/block records have *different URIs* from their subjects.
- **Reply roots.** When replying to a reply, root comes from ancestor chain, parent is immediate target.
- **Text facets.** Incoming facets use UTF-8 byte slices. Validate boundaries; handle combining marks, emoji and malformed input. For outgoing mentions resolve DID; don't create a facet pointing to an unverified handle.
- **Auth route.** Authenticated calls generally go to user PDS and are proxied where necessary. Do not send session bearer tokens directly to arbitrary media/CDN URLs. Use SDK routing/proxy utilities.
- **Label handling.** Keep notices visible and honour the local warning preference and explicit mute/block state. This is not a complete server moderation-preference engine.
- **Union types.** Views include records unavailable due to deletion, block, moderation, unsupported embed; degrade gracefully rather than crash.
- **Time.** Parse UTC timestamps with timezone, convert with local system timezone, relative display should update sanely.
- **Pagination.** Cursor may be null, absent, repeated or stale; prevent loops and duplicate records. Respect rate limits.
- **SDK signatures.** The namespace method invocation may use generated `Params`/`Data` objects rather than keyword arguments; inspect installed version and docs. High-level helpers can differ from raw XRPC.

## Authoritative verification

- https://bsky.network/docs/bluesky-api/
- https://atproto.blue/
- https://atproto.blue/guides/posting/
- https://atproto.blue/guides/authentication/
- https://endpoints.bsky.app/

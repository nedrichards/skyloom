# Validation status

Live-account interoperability and human accessibility/hardware acceptance remain
open; see [ROADMAP.md](ROADMAP.md). Default-renderer scrolling has no accepted
matched performance baseline. Distribution follow-up is tracked in the roadmap.

## AppStream showcase links — 14 November 2026

Added the existing light/dark showcase screenshot URLs and the published 0.1.1
release URL. Offline and online `appstreamcli validate` passed. All three URLs
returned HTTP 200 in host-side checks. Screenshot files were not changed.

## Taller aspect-aware image previews — 14 November 2026

Image embeds now retain validated optional aspect dimensions through immutable
models and cached posts. The pinned atproto 0.0.74 `ViewImage.aspect_ratio`
contract was inspected. Preview height follows available width and source shape,
bounded to 160–560 logical pixels, with a 4:3 fallback. Extreme shapes retain a
centred crop. Download-policy placeholders, failure and eviction share reserved
geometry; decoded pixel dimensions never trigger a height change. No subject
analysis or additional decoding/network work was introduced on the scroll path.
No measured performance improvement or physical-scroll acceptance is claimed.
The user confirmed the updated image presentation looks good in manual testing.
Local lint, desktop/schema validation and the initial 378-test source suite
passed. The pinned offline build/export and install passed; all 56 installed
Python modules matched source (Flatpak commit
`ea5897359d0230ccedaca96f43c7026d428062af35ee3d2ce39145f66f9f8c55`).
The expanded 380-test installed default-renderer run hit a feed-selector layout
settling timeout; an isolated rerun passed that check but hit a native text
selection assertion. Image geometry, model validation and cache tests passed.
The complete installed X11/Cairo suite then passed all 380 tests with zero skips.
The installed default-renderer navigation smoke passed at 1280/light and 480/dark;
both captures were visually inspected. These results do not establish measured
scrolling performance.

## Feed-management menu focus — 14 November 2026

The installed demo's actual menu row reached Gtk.UriLauncher, and the user
confirmed that the browser opened the saved-feeds page. The original tap failure
was not reproduced. Removed a possible rejection path: feed management now
accepts main-menu/closing-popup focus and remains enabled while a menu is open;
account and visible-dialog guards remain. A regression covers list, popup and
chrome contexts with an already-dismissed menu, plus visible-dialog rejection.
Local lint passed. The updated Flatpak was built offline, exported and installed
(commit `80ee2dd8cc6dc1abeb92bc1967ca9c342babaa88ee202223589ca2ac128c4abe`);
all 56 installed Python modules matched source. All 378 installed native tests
passed with zero skips. The user confirmed the updated action works in manual
testing. No further GUI smoke was needed after that confirmation.

## Saved-feed preference handling — 14 November 2026

Feed loading now uses the latest V2 preference when present, including an empty
one; legacy pinned feeds are a fallback only. Generator responses are mapped back
to saved URI order, with duplicate URIs removed. Distinct feeds with the same name
remain distinct. Following remains fixed first; list feeds are not supported.
The main menu links explicitly to Bluesky’s saved-feed editor; native editing
remains roadmap work. Restart to reload website changes.
Upstream agent preference migration and the saved-feeds route were verified.
Local lint, compilation, desktop/schema validation and the host Flatpak source
suite passed: 377 tests, zero skips. The combined check script could not run
wholly in one environment (sandbox Flatpak namespace restriction; host venv lacks
Ruff), so its lint and native portions ran separately.
The pinned offline Flatpak build/export and local installation then passed
(commit `ecf066bf697a06e8b3250938672e02dabbdd1936f2fff78cb3b314d6f17ccd25`).
All 56 installed Python modules matched source, and all 377 installed tests passed
with zero skips. The installed default-renderer navigation demo smoke passed at
1280/light and 480/dark; captures were visually inspected. A temporary installed
app check verified the feed-management label, registered action and exact browser
destination, intercepting the opener without opening the browser. Live-account
comparison and human acceptance remain unperformed.

## Shared profile identity/actions row — 14 November 2026

Corrected the remaining layout issue: the controls are now children of the same
adaptive identity row as the name and handle, for both own and other profiles.
Wide layouts place actions beside the identity; narrow layouts wrap within that
header instead of leaving an action row below the biography and statistics.
Long names/handles retain wrapping and native selection. Native tests assert
both profile types share the row at 1280 pixels and remain usable at 480 pixels;
the installed profile smoke now also captures and checks both wide headers.
The updated installed suite passed all 375 tests with zero skips under X11/Cairo.
The installed default-renderer profile smoke passed, including both 1280-pixel
headers and the 800/480-pixel layouts. Both wide captures were visually inspected.
The seven focused profile/compact-header checks also passed.

## Confirmed-write reconciliation — 14 November 2026

Audited all requested mutations. Profile and mute/block saves now use successful
write inputs/results without a dependent AppView read. Session-scoped, bounded
confirmations protect identity/images, relationship fields and reactions across
service and cached reads for two minutes. Read markers use the confirmed cutoff,
and unread counts pass it explicitly through the pinned SDK's `seen_at` parameter.
New posts retain their returned URI/CID and submitted immutable content while
missing from compatible head pages and reply threads; indexed records win.
Publishing refreshes the active profile/thread as well as Home, and later draft
cleanup failure is reported as successful publishing with a cleanup problem.
Existing deletion tombstones, bookmark overlays and repository gate writes remain
in use; mutation target validation has not been weakened.

Contract verification used the installed/pinned atproto 0.0.74 generated
notification parameter model and async-client write response types. The complete
source suite passed 373 tests, and after the final text-only profile preservation
check, the installed suite passed all 374 tests with zero skips under X11/Cairo.
The pinned offline Flatpak build/export and local installation passed; all 56
installed Python modules matched current source. The full installed demo GUI
smoke passed with the default renderer, including publishing/drafts, profiles,
notifications, reactions, conversations, offline recovery and responsive
light/dark layouts. The compact profile capture was visually inspected. The direct
`check.sh` run passed lint, formatting, compilation and desktop/schema checks,
then encountered the nested Flatpak instance boundary; native runs use the host
Flatpak route. Live service propagation, delays longer than the two-minute
confirmation window, cross-device edits during that window, and physical
accessibility acceptance remain unverified. No account mutations were performed
against a real service and no mutations were retried automatically.

## Profile refinements — 13 November 2026

Profile actions wrap at minimum widths rather than reserving the post filter's
longest natural label. The banner now sits above the identity with the avatar
crossing its lower edge. Successful edits retain the prepared banner on the
current page while AppView indexes the write, including explicit removal.
Image completions now bind to the replacement view rather than the closed view.
Optional content warnings retain ownership of hidden banner imagery.

Lint, formatting, desktop/schema validation passed; the direct `check.sh`
runtime stage hit the nested Flatpak instance boundary. The host-launched source
suite passed 355 tests. An initial installed Wayland run exposed an unrelated
popup-mapping failure and an incorrect new test assumption that `profile()`
returns its page; that test now reads the visible navigation page.
The offline Flatpak build/export and local installation succeeded. The installed
suite passed 356 tests with zero skips under the documented X11/Cairo gate.
After the final image-callback and fixed-height crop changes, an installed
native rendering check passed: a saved fixture banner acquired its paintable,
kept a 160-pixel crop, and the Edit profile/browser/Posts controls stayed on one
row at both 480 and 800 pixels. Invented screenshots were visually inspected.
The installed profile GUI smoke passed with the default renderer, covering
expanded/compact headers, scrolling, return, and own-profile layouts.
Live uploads, server indexing timing and physical accessibility acceptance
remain unverified.

## Skyloom 0.1.1 — 13 November 2026

Recorded the SDK, profile, post-management and video work as four semantic commits
and pushed them to `main`. Prepared 0.1.1 across Meson, Python package metadata,
the application version and AppStream. Updated release wording, added project
URLs and release notes, and changed the README to
the hosted release bundle instructions. The repository retains its private visibility.

The canonical host-launched `./scripts/check.sh` passed all stages, including
355 native tests with zero skips. The independently staged profile slice passed
17 focused tests and the post-management slice passed 72. The pinned offline
Flatpak build/export passed, and the exact exported x86_64 bundle installed as
0.1.1 with atproto 0.0.74. All 55 installed Python modules matched source; its
complete installed suite also passed 355 tests with zero skips. AppStream
validation passed; its pedantic note concerns uppercase characters in the
established application ID. The release bundle is accompanied by `SHA256SUMS`.
The full installed 0.1.1 demo GUI smoke passed with the normal desktop renderer;
frame-timing warnings remain visible. Live-account and human acceptance limits
remain documented below and in the roadmap.

## atproto 0.0.74 — 13 November 2026

Verified the latest release from live PyPI metadata and the upstream changelog:
[0.0.74](https://pypi.org/project/atproto/0.0.74/) was released on 12 November
([release notes](https://github.com/MarshalX/atproto/blob/main/CHANGES.md#version-0074)). Updated `pyproject.toml`, runtime/development
locks, hashed requirements and the Flatpak dependency manifest. The wheel digest
was checked against PyPI; all other dependency versions and wheel pins remain
unchanged. `pip check` passed. The maintained dependency generator timed out on
the sandbox's Python network route and completed through the host route.

The SDK boundary now uses the public serializer for models, blobs and unknown
`DotDict` records, replacing three duplicated serializers. This fixes attribute
probing that could mistake a missing `DotDict.model_dump` for a callable method.
Five new regression tests cover unknown records, nested extension fields in
profile/gate write round trips and typed page-item access without dumping unused
response metadata. Feeds, profile feeds, search, people and bookmarks use the
new page-item interface; notifications map typed fields directly, avoiding
serialization of unused embedded post records. Each UI request still loads one
page, with the existing bounded windows, cursor protection and cancellation.
The SDK's parsing changes apply without bypassing its validation. No performance
claim is made from the upgrade.

Twenty focused SDK/profile/thread contracts passed with 0.0.74. The rebuilt and
installed GNOME 51 X11/Cairo suite passed **355 tests with zero skips**. The pinned
offline build/export/install passed, the installed SDK version is 0.0.74, and all
55 installed Python modules matched source. `./scripts/check.sh` passed its
non-runtime stages and hit the nested Flatpak instance boundary; the host-launched
installed suite supplied the runtime gate. The full installed demo GUI smoke
passed with the normal desktop renderer; frame-timing warnings remain visible.
Live service interoperability remains unperformed; existing human acceptance
limits below still apply.

## Account and post features — 13 November 2026

Implemented private server bookmarks, own-profile editing, follower/following
browsing, reply/quote permissions, hidden replies and detached quotes, plus native
video playback and upload. Post deletion retains content-stripped placeholders
and persistent tombstones. Mutations use ownership/session guards and never queue
offline or retry automatically. Bookmark reconciliation covers AppView lag and
queued cache checkpoints; deleted bookmarked posts remain removable.

The final installed GNOME 51 X11/Cairo suite passed **350 tests with zero skips**.
Coverage includes actual pinned-SDK HTTP contracts, destructive confirmation,
record conflicts and session changes, native lists/dialogs, failed-edit/draft
recovery, metadata-stripping ffmpeg preparation and sign-out cleanup. An invented
H.264/HLS stream decoded and rendered frames with advancing timestamps; native
mute/volume delegation passed. The built-in GTK media backend failed HLS here,
so playback uses GStreamer URI decoding exposed through `Gtk.MediaStream` and
native `Gtk.Video` controls. Upload checks quotas, streams bytes once, validates
processing jobs and polls with a finite deadline. MP4/H.264/AAC clips are limited
to 10 minutes/300 MB; no lossy transcoding is included.

`./scripts/check.sh` passed its lint/format/compilation/shell/desktop/schema
stages, then hit the nested Flatpak instance boundary. Its native runtime stage
was supplied by the full host-launched installed-app suite above. The pinned
offline Flatpak build/export/install passed, all 54 installed Python modules
matched source, and the sandbox permission review confirmed the audio socket
needed for playback. At this feature gate, no dependency version/hash pins changed;
the subsequent SDK upgrade is recorded above.

The full installed demo GUI smoke passed with the normal desktop renderer after
the navigation assertion update. Invented-data captures of the new profile
editor, bookmarks page, thread controls and video composer were inspected at
480 pixels, with normal styling and high contrast/16-point text. Controls wrap
and long dialogs scroll. The review script was temporary; captures stay ignored.

The first integration run exposed old widget fixtures missing account context
and an HLS readiness assertion that ran before the first rendered frame. Both
were corrected without removing assertions. The smoke runner's destination
assertion now includes Bookmarks. A GDK skipped-frame warning occurred in the
otherwise passing native suite, and the GUI smoke emitted frame-timing warnings;
no performance improvement is claimed.

Live-account deletion/indexing, bookmark synchronisation, profile/media upload,
gate propagation and remote playback remain untested. No real account was
mutated or captured. Physical input, audible output, Orca and accessibility
acceptance remain open; the automated pipeline/mute tests do not prove them.

## Post deletion — 13 November 2026

Own-post menus now offer confirmed deletion. The service validates the signed-in
repository, post collection and displayed record CID before `deleteRecord` with
`swapRecord`; a missing record is already deleted. There is no mutation retry or
offline queue. Deleted placeholders strip content/media/actions while retaining
reading position and thread edges. Account-local tombstones prevent stale AppView
responses and cache checkpoints from restoring deleted content; thread snapshots
and nested quotes reconcile the same deletion.

The affected service/domain/storage tests passed 51 tests in the installed GNOME
runtime using checkout modules and invented HTTP records. Twelve focused deletion
and thread-cache tests also passed. Ruff passed. The host Python environment lacks
GI and nested Flatpak execution cannot allocate an instance, so these checks ran
through the permitted host Flatpak route. Combined installed-module and full native
evidence is above. No live post was deleted; live-service
propagation, physical input and accessibility acceptance remain unperformed.

## Repository cleanup — 13 November 2026

Removed historical documentation, benchmark output, generated icon previews and
routine smoke captures. Two invented-data showcase images remain. Shortened the
README and kept reusable development/profiling tools. No dead application code
was confirmed, so the large application modules remain intact.

Native tests share display setup and content/startup fixtures. Meson now uses
the strict runtime runner. A no-display run exposed a crash after GTK reported
successful initialisation without a default display; preflight now rejects that
state with exit status 2. The optional keyboard harness also rejects missing
injected input before testing selection.

The source suite passed 289 tests with zero skips before and after fixture
cleanup in host-launched GNOME 51 Flatpak under X11/Cairo. Lint, formatting,
compilation, shell syntax, desktop/schema validation and local documentation
links passed. Direct `check.sh` cannot cross the agent's nested Flatpak boundary;
its runtime stage was run separately through the host. Meson setup/compile, its full 289-test run with zero skips, and the offline
pinned Flatpak build/export/install passed. The installed keyboard harness hash
matches the source. The full installed demo GUI smoke passed with the normal
desktop renderer. The two showcase images were refreshed from that run and
visually checked; other captures remain ignored.

XTest reported successful sends but GTK received zero key events in both installed
and source keyboard runs. The corrected harness reports this as unavailable input,
not a failed J shortcut. Physical input acceptance remains open. GDK emitted a
skipped-frame warning during otherwise passing native runs; no performance claim
is made.


## Profile editing and follow browsing — 2026-11-13

Own profiles now offer a native editor for display name, description, avatar and
banner. The PDS record snapshot preserves labels, pinned posts and unknown fields;
writes use the original CID (or create the absent literal `self` record) and are
never automatically retried. Name/description limits include graphemes and UTF-8
bytes. Images reuse metadata-stripping, bounded preparation. Failed saves retain
entered values; account/generation guards reject stale completions. AppView may
index new profile images after the successful PDS write; refreshing the profile
loads the current indexed images.

Follower and following counts open bounded, cursor-paged native people lists,
sharing virtualised rows, one scrolling surface, profile activation and retry.
The atproto 0.0.73 SDK already provided the required profile repository and graph
endpoints; the 0.0.74 upgrade above supersedes that dependency evidence. Eight actual-SDK mock contracts and three
native demo integration tests passed in the installed GNOME 51 runtime with source
modules under X11/Cairo. These cover metadata preservation, record conflicts,
missing profiles, invalid images, ownership, cursor/viewer mapping, failed-edit
retention and navigation. They do not establish live account interoperability or
physical-input/Orca acceptance. Full build/install verification is recorded with
the combined feature gate.

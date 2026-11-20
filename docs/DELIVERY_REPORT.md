# Validation status

Live-account interoperability and human accessibility/hardware acceptance remain
open; see [ROADMAP.md](ROADMAP.md). Default-renderer scrolling has no accepted
matched performance baseline. Distribution follow-up is tracked in the roadmap.

## Multi-image post grids and text links — 20 November 2026

Shared post rows arrange multiple photos in two columns, cap preview heights,
and reuse their image cells and viewport-managed requests. A three-photo post
spans the first image across both columns. Selecting an image opens its position
in the existing gallery. A click on an inline link, mention or tag now dispatches
its browser action through the post label. Text selection and plain-text
conversation activation still use the label and row gestures.

The offline Flatpak export was installed as commit
`72b28ab79ace38555a24d7a2fee2b7b969cc7b20223549eb3417a403f6ff6156`
and its post widget module matched source. The installed media smoke verified
zoom and gallery navigation. Invented posts rendered as a four-image grid at
480 pixels in dark mode and a three-image grid at 800 pixels in light mode.
A private Xvfb display delivered mouse clicks to invented link, mention, hashtag
and regular text targets. Each dispatched its expected action once. The harness
recorded browser destinations without opening them. Lint, desktop entry and
schema checks passed. The first default-display run hit two layout-settling
failures. The final installed suite passed all 413 tests with zero skips under
X11/Cairo. Physical touch, a live feed and scrolling performance remain
unmeasured.

## Saved feed position startup reveal — 18 November 2026

Startup keeps an opaque loading page over a saved viewport below the feed head
while the virtualized list positions its rows. The reveal waits for position
correction and a settled frame, then fades the loading page away before showing
the feed selector. Reduced motion reveals the settled feed without a fade.

`./scripts/check.sh` passed 412 tests with zero skips. The exported Flatpak
was installed as commit
`0d816489e39ee326708e6b17828904c99a043c08e7fa81c2e7a843d4165ad28e`.
Both installed startup tests passed. An installed-app fixture with 150
invented mixed-height posts restored post 110 at its saved −32 logical-pixel
offset in both animated and reduced-motion modes.

## Content-warning focus on headless Wayland — 18 November 2026

Both Wayland jobs in GitHub Actions run 44341566239 failed the same
Show content focus assertion. Both architectures passed their X11 generated
cases and latest-SDK jobs. The content-warning handler now checks the
toplevel's remembered focus before switching controls. The regression test
sets that focus in an inactive GTK window and verifies both handoffs without
requiring a compositor keyboard seat.

The new assertion reproduced the focus failure before the fix. The final
x86_64 GNOME 51 source suite passed 412 tests with zero skips under local
headless Weston 16. Both installed focus tests and the installed labels smoke
passed there. The offline Flatpak export was installed as commit
`048108ffab91949c20b88862e44295a46d9afcf8ee0d78f09a8fc5b61fcd20be`;
the installed content module matched the checkout. Lint, desktop metadata
and schema checks passed. The desktop-display test attempt stalled on an
unrelated scroll test and was stopped before switching to isolated Weston.
The hosted runner used Weston 15. Hosted validation of the fix remains open.

## Image gallery navigation — 18 November 2026

The viewer starts at the clicked thumbnail and shows Previous, Next and the
current position for multi-image posts. Arrow keys navigate in Fit mode while
preserving description selection and zoomed panning. Switching images resets
zoom and pan, updates the description and browser action, and rejects late
results from superseded loads.

`./scripts/check.sh` passed 411 tests with zero skips. The offline Flatpak
export was installed as commit
`21fb9c41f67dd0e2186bde5d0a8f2b6f6ddb4e754b60ce0be4c5631c13067df8`;
all 57 Python modules matched the checkout. Both focused installed viewer
tests and the installed media smoke passed. Reviewed the gallery header at
480/dark and 1280/light. Physical keyboard and screen-reader acceptance
remain open.

## Image viewer controls — 18 November 2026

The native viewer adds Fit, zoom controls and percentage, mouse drag and
native scrolling on both axes. The description keeps its copy action and can
be hidden or scrolled separately. Portrait images use a side description at
wide sizes, and other layouts place it below the image.

`./scripts/check.sh` passed 410 tests with zero skips. The offline Flatpak
export was installed as commit
`0bf1fd8aed9b6d332e76ea9b04a210e9a68d7d11fa191c4da60ff71883cbd888`;
all 57 Python modules matched the checkout. The focused installed test covered
retry, decoded aspect fallback and responsive placement. The installed media
smoke exercised 400% zoom, both pan adjustments, Fit, and a long description.
Reviewed installed demo captures at 1000/light and 480/dark. Physical gestures
and screen-reader acceptance remain open.

## Viewport media geometry — 17 November 2026

Traced the installed GNOME 51 app under Wayland/Vulkan with 150 invented posts,
eight seconds per direction at 6,000 logical pixels per second. Each run covered
about 95,000 logical pixels over the two scroll phases with zero row rebinds.

| Feed | Width | Media passes | Widget bounds calls | Candidate row bounds calls | Widget calls skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed photos and video thumbnails | 1100 | 477 | 1,009 | 0 | 0 |
| Mixed photos and video thumbnails | 480 | 477 | 1,032 | 0 | 0 |
| Two-image posts and quotes | 1100 | 476 | 1,249 | 497 | 0 |

The mixed feed supplies one media widget per row. The gallery trace supplied
multi-widget candidates, but none were fully outside the retention band. A
row bounds precheck would have added 497 calls in that run. Skyloom keeps
its existing per-widget load and eviction thresholds. These are call counts
from scripted scrolling with trace instrumentation. Physical momentum and
general scrolling performance remain unverified.

`./scripts/check.sh` passed 409 checkout tests with zero skips after the trace
change. The trace ran in the installed Flatpak against its existing app modules.

## Request recovery, image cache and reading prototypes — 17 November 2026

Repeated worker admission failures keep distinct request identities. A publish
failure before the draft save confirms that publishing did not start and leaves
the current revision editable. The encoded image cache indexes size and recency
after the initial scan and rebuilds that index following an I/O failure.

In a local probe at the 2,048-file cap, 40 warm writes per version took a median
of 19.21 ms before indexing and 0.70 ms after indexing. The probe used tiny
invented payloads on a temporary filesystem and measured only cache writes.

The Home prototypes show the previous reading position after a jump and preview
an eligible retained parent from the conversation pill. Inline video resume
keeps seek positions in memory and requires an explicit play action. Native
coverage exercised the marker and Undo position, moderation updates while a
preview is open, and an actual seek in a generated video after unmapping.

The host GNOME 51 checkout and installed suites each passed 409 tests with zero
skips. An offline Flatpak build exported and installed commit
`bfb393ae2eb84bcf46abb0ad368419c323fc3a0ac1d1c3b22b188132c1d49d29`;
all 56 installed Python modules matched the checkout. The installed refresh
smoke passed. Installed demo captures at 800/light and 480/dark showed the
reading marker and parent preview, and the marker preserved measured row height.
Live-account behaviour, physical input and screen-reader acceptance remain open.

## Relative timestamps — 16 November 2026

Added one window-owned 60-second BOOTTIME timer, including resume catch-up,
activation and mapped-card refresh. Weakly held bound rows share one current
time per tick; unchanged labels are untouched and cancelled rows unregister.
Timer sources and file descriptors close with the monitor. Focused native tests
cover row filtering and unchanged-label suppression.

Lint, formatting, compilation, desktop and schema checks passed. The restricted
sandbox could not start Flatpak (`Unable to allocate instance id`), but the
host route built/exported and installed commit
`adb4bba4f0e86b614e89893a7a0e1b9f7be40b7f6b812e87bd7449ed7e6ab3c7`.
Both changed Python modules matched the build output by SHA-256. Subsequent
host native validation passed all 405 tests with zero skips and dependency
parity for 22 packages on both architectures. The existing manually constructed
monitor fixture now initializes the timestamp timer fields; close clears its
timer source after removal. The user
reported the installed change working well. No measured performance claim is made.


## Alt text reading preference — 15 November 2026

Added a persistent, default-off “Always show alt text” switch under Reading.
Post images keep their accessible descriptions and clickable viewer; the viewer
continues to show nonempty descriptions and Copy description independently of
the preference. Changing the setting refreshes existing lists through the
reading-position-preserving media redisplay path. Empty descriptions remain
hidden, and recycled cells clear captions when disabled.

Native coverage checks the default, opt-in captions, recycled-cell clearing,
accessible image labels and viewer activation. The existing recycling fixture
explicitly opts into captions; the Preferences GUI smoke toggles the new switch.

`./scripts/check.sh` passed all 403 tests with zero skips, plus lint, formatting,
compilation, desktop/schema and dependency parity checks. Offline Flatpak
build/export/install succeeded. The installed full demo smoke completed the
preference toggles and image-description overlay steps, then terminated with
status 143 during later conversation checks without a smoke completion marker.
The focused installed Preferences smoke then passed, including the new toggle
and wide/narrow light/dark captures. The narrow Preferences capture was
inspected: the new switch fits and is off.
No live-account or physical-input acceptance is claimed.

## dnspython security update — 14 November 2026

Updated only dnspython from 2.9.0 to 2.9.2 across runtime/development locks and
the generated hashed lock and wheel manifest. The universal wheel was downloaded
and verified against PyPI SHA-256 metadata; it serves both x86_64 and aarch64.
The existing generator preserved every other package version, URL and hash.
Upstream's patch addresses excessive resource use when parsing malicious
zone-file WKS records (GHSA-vvf4-9x63-8xvv). An installed check confirmed version
2.9.2 and rejected the small, out-of-range service-number example with SyntaxError.

Dependency parity, lint and all nine maintenance checks passed. The live PyPI
health report verified all wheel digests and reported no remaining advisories.
Build/export/install passed (Flatpak commit
`032a75fb0e841d1bf8a156b404e5f109e795d2dd4e9732d30dfa1ea2aec38613`).
All 402 source and all 402 installed tests passed with zero skips on an isolated
composited X11/Cairo display. Earlier runs on the user's desktop encountered
popover mapping and keyboard-window rendering/positioning failures; these were
retained in ignored logs and no assertions were suppressed. Isolated display
validation avoids desktop occlusion and does not establish physical-input or
live-service acceptance. Hosted ARM64 validation is tracked separately.
The installed navigation smoke also passed at wide/light and narrow/dark sizes.

## Dual-architecture workflow implementation — 14 November 2026

Added PR/main validation, dependency health, extended generated cases, latest-SDK
and advisory Wayland checks, and verified release packaging for both native
x86_64 and aarch64 runners. Application jobs share the official Flathub GNOME 51
container and SHA-pinned Flatpak Builder action. The pinned OCI index was checked
live and supplies linux/amd64 and linux/arm64 images. Workflows do not install
Flatpak on the Ubuntu runner or modify runner kernel settings. Two pinned source
archives provide CI-only Openbox/xcompmgr helpers inside the build container;
both compiled and loaded successfully in the local Builder environment.

Release preparation resolves the tag once for both builds, validates its version,
records application/tooling commits and any packaging overlay, and requires both
architectures to pass before attesting bundles/build information and optionally
creating a draft. Existing releases cannot be overwritten. No release is
published automatically. A disposable checkout of the real 0.1.2 tag passed
source/overlay preparation; mismatched and malformed tags were rejected.

Local actionlint 1.7.12, stable/selected-preview Ruff, formatting, compilation,
shell syntax, dependency parity and all nine maintenance checks passed. Three
generated-boundary tests passed 1,000 cases each. `./scripts/check.sh` passed
399 source tests with zero skips before the final three CI maintenance tests
were added; those passed separately. The agent sandbox could not allocate a
nested Flatpak instance. Host-side validation used GNOME 51 and the existing
pinned Ruff binary because host Python 3.15 cannot use the Python 3.14 venv.
The offline x86_64 build/export/install passed (Flatpak commit
`4442c52ae910eaa49f4945bd9bd610f6add9f0c00032aafbf19d8dfcf1379546`).
All 56 installed modules matched source. The final installed X11/Cairo suite
passed 402 tests with zero skips, including 1,000 cases per generated-boundary
test. An earlier default-Wayland installed run failed the existing feed-switcher
header-resize settling assertion; it is retained as a limitation, not suppressed.
The complete installed X11/Cairo demo smoke and separate high-contrast/large-text
navigation variants passed sequentially, producing 54 invented-data screenshots
and an HTML contact sheet. The wide high-contrast and narrow large-text captures
were visually inspected. These are functional/layout evidence, not physical
input, Orca or default-renderer performance acceptance.

The live PyPI health report verified all pinned wheel URLs/digests and correctly
failed for dnspython 2.9.0's published GHSA-vvf4-9x63-8xvv advisory. Production
dependency pins remain unchanged; the coordinated patch update is in the roadmap.
The SDK probe uses pip from the SDK to prepare a disposable overlay, then runs
the installed application against that overlay; the production Platform has no
pip. The local probe resolved atproto 0.0.75 with all other production pins constrained;
all 402 installed X11/Cairo tests passed against that disposable overlay with
zero skips. The production SDK pin remains 0.0.74. Hosted image startup, native
ARM64 execution of these new jobs, scheduled runs, draft creation and signature
verification still require GitHub execution.
No workflows have been dispatched and no commits, releases or tags published
as part of this implementation.

The implementation was subsequently committed and pushed as `6104451`. Its
first hosted CI run started both native container architectures and exposed two
CI-specific setup failures: ShellCheck SC2035 on release asset globs, and Git's
ownership check after the second checkout replaced the first checkout's temporary
safe-directory configuration. The follow-up qualifies asset paths and supplies
exact per-command checkout trust without changing global Git configuration.
Both hosted source jobs subsequently passed. The ARM64 helper build exposed
Openbox's bundled 2008 `config.guess`, which predates aarch64. CI now refreshes
both GNU config scripts from Automake in the pinned image before configuring
the helpers, and streams the saved setup log into the job log.
The first x86_64 build then exposed OSTree's `Invalid cross-device link` while
updating preinstalled runtimes in Docker image layers. The native container now
uses an anonymous `/var/lib/flatpak` volume, initialised from the image, so runtime
updates stay on one filesystem. Build information records the validated runtime
and SDK commits after Builder has finished. The custom Openbox prefix is also
included in its XDG data/config paths so its installed themes can be found.
Both hosted builds subsequently installed successfully and reached the native
suite. The CI-summary regression now directs its summary into its temporary
fixture directory instead of inheriting a runner path inaccessible inside the
application sandbox. Installed image tests exposed missing Flatpak portal
activation in the minimal build container; the display session now starts that
portal explicitly and preflights sandboxed PNG encoding before the suite. The
container also provides the conventional D-Bus daemon path expected by its
accessibility launcher. Decoder sandboxing remains enabled.
The minimal container's D-Bus build uses `/app/var/lib/dbus`, which is absent
from the image. Session preparation creates that directory and shares its
generated machine ID with the conventional container paths before starting the
portal, keeping the portal alive for the full sequential test session.
The container exports one explicit runtime directory before Builder and portal
startup so installed apps, the session bus and decoder subsandboxes share the
same Flatpak instance registry.

## Native ARM64 packaging — 14 November 2026

A native GitHub-hosted ARM64 builder validated the same 0.1.2
application source. All seven compiled dependencies have aarch64 wheels at the
existing pinned versions. Downloaded wheels were verified against PyPI metadata;
architecture filters preserve every prior x86_64 URL/hash and select one complete
22-package set per architecture. The builder uses read-only repository permission,
SHA-pinned GitHub actions, a fixed version tag and a checked packaging overlay.
Local generator checks and the offline x86_64 build passed. The initial native
ARM64 build/install/source-parity check succeeded; 393 of 394 tests passed, with
one exact header-resize expectation failing under the non-composited Xvfb setup.
The builder now supplies an X11 compositing manager and runs that unchanged test
as a preflight before the full suite. The unchanged preflight and all 394 installed
tests passed with zero skips, followed by the installed navigation GUI smoke at
wide and narrow widths. All 56 installed modules matched the fixed release source.
[Successful native run](https://github.com/nedrichards/skyloom/actions/runs/43617280851)
records application commit `fe3fa3e` and packaging commit `5e4f26b`. The downloaded
ARM64 bundle passed its published CI checksum. Physical ARM64 desktop acceptance
remains outstanding.

## Release 0.1.2 — 14 November 2026

The user confirmed both sustained feed scrolling and remote video thumbnails
work well and requested a new release. Version 0.1.2 collects the changes since
0.1.1: inline playback and thumbnails, larger aspect-aware media, bounded active
reading windows, profile header/banner improvements, confirmed-write consistency
and saved-feed management fixes. Runtime and dependency pins remain unchanged.
The x86_64 release bundle was built/exported/installed from the pinned GNOME 51
manifest (Flatpak commit
`bd7af7312cc8973b832ae2b817b8143678ee1cb91baffba63d973d47c51d3d36`).
All 394 installed native tests passed with zero skips, and the complete installed
demo GUI smoke passed on the default renderer. Wide/light and narrow/dark feeds
and the profile header captures were visually inspected. All 56 installed Python
modules matched source; application version 0.1.2 and SDK 0.0.74 were verified.
AppStream offline validation passed, sandbox permissions were unchanged, and an
installed-data audit found no environments, databases, logs or credential files.
The bundle includes Flathub runtime discovery for fresh installations. It is
accompanied by `SHA256SUMS`; the bundle SHA-256 is
`f0b3330c99620fdca6c6e389122d99f9f75cfe183e5820ab5a9f574730b2f9f9`.
Broader live-service, physical-input and accessibility limits remain in the roadmap.

## Video thumbnail transport follow-up — 14 November 2026

Approved inline playback and scrolling work was committed and pushed as
`45d9eaa` on `main`, with origin/local parity and a clean worktree before this
follow-up. The user then reported no video previews despite working playback.
The model retained the supplied thumbnail URL, but the image loader accepted
only `cdn.bsky.app`. A HEAD request to Bluesky's own public announcement-video
thumbnail confirmed a 302 from `video.bsky.app/watch/…/thumbnail.jpg` to
`video.cdn.bsky.app/hls/…/thumbnail.jpg`; the old loader also disabled redirects.
No signed-in feed, credentials, cookies or personal records were inspected.

The follow-up accepts those exact HTTPS thumbnail routes and up to two checked
redirect hops, with no wildcard domains or playlist downloads. Photo-CDN
redirects remain disabled. The image byte/pixel bounds, worker semaphore,
account cache keys and automatic-download policy remain. Six native regression
tests use invented requests and generated PNG bytes for redirect/decode/cache
round trips, unsafe initial/redirect targets, redirect loops, the photo policy
and the response byte cap. All 394 source native tests passed with zero skips;
lint and desktop/schema validation passed. Offline build/export/install passed
(Flatpak commit `13f9af4b019a0be6247e0adff41306efcdae90fe0a4993ccd143dfdecf086111`).
All 34 installed worker/image/cache/residency/thumbnail/player/playback checks
passed with zero skips. The installed image loader also followed the actual
public Bluesky thumbnail redirect and decoded a 1600-by-920 texture, in memory
only, without an account or saved image. This establishes service transport and
decoder interoperability, not acceptance on the user's signed-in feed. The
user confirmed the follow-up works well. It is committed separately from the
earlier media and scrolling changes.

## Sustained mixed-height feed scrolling — 14 November 2026

The user reported that pixel-only redraw improved scrolling but did not resolve
severe stalls on longer scrolls. A new 12-second-per-direction, 6,000-pixel/second
mixed-media trace reproduced the problem in the installed previous build:
1,972/2,644 native row binds and 1,672/1,904 media measurements during forward/back
scrolls of about 72,000 pixels each. Peak paint spans were 116.2/116.1 ms, including
54/71 spans above 50 ms. Slow frames rebound about 45 rows even without downloads.
The supported GTK 4.24.1 source confirms a 200-widget list tracker and median
estimates for unknown row heights. A below-capacity control removed that cycling.

Active post/record windows now hold 150 items, leaving room for normal gap/footer
rows below that tracker budget. This changes data windowing, not media geometry:
the aspect-aware images, thumbnails, centred crop and explicit inline playback
remain. Archive retention is unchanged. Existing saved windows of up to 250 posts
are narrowed on the worker around the bookmark; archived page metadata supplies
real continuation boundaries. No safe boundary means the readable legacy window
is retained until normal reconciliation, rather than skipping data or inventing
a cursor. The conversation graph's separate limits are unchanged.

The candidate trace recorded zero row binds and zero media remeasurements in
both scroll directions, with 71,895/71,408 pixels travelled and peak paint spans
of 26.1/25.4 ms (one span above 25 ms in each direction, none above 50 ms).
This is a diagnostic comparison on Wayland/Vulkan with local fixture pixels;
trace overhead, differing active row counts and the absence of physical momentum
or real download latency preclude a universal frame-rate claim. A native regression
also scrolls a mixed portrait-photo/landscape-video window in both directions and
asserts no rebinds. Archive tests check five legacy bookmark positions, exact
cached continuation and retention of all archived records. The initial 388-test
source suite exposed one old assertion expecting all 240 saved rows to remain
active; it now checks the narrower window while keeping anchor/offset/selection
and refresh assertions. All 21 focused startup tests then passed. A final
missing-anchor migration case resolves the saved neighbour before narrowing;
all ten archive/window tests passed with that case. The final offline
build/export/install passed (Flatpak commit
`ae181942ddbe7ed4e339202fef469264e0551ebdae262830ac42093871570426`).
All 388 final installed default-renderer native tests passed with zero skips,
and all 56 installed Python modules matched source. The installed long trace
confirmed zero binds/unbinds/remeasurements in both directions, roughly
71,937/71,442 pixels of travel, and peak spans of 25.7/29.9 ms. Initial allocation
of newly encountered media still occurred, as expected. Installed thumbnail,
narrow playback and fallback captures were visually inspected, and the actual
app's navigation smoke passed at 1280/light and 480/dark. The final anchor-only
correction does not change those widgets. The user subsequently confirmed that the scrolling fix works perfectly.
Remote video thumbnails still do not appear in the live feed despite working
playback; that delivery path is a separate follow-up.

## Media scrolling layout churn — 14 November 2026

The user confirmed inline video works, then reported judder as differently sized
media entered the feed. A mapped fixed-rectangle probe showed that replacing or
evicting native picture paintables still caused 55 preview measurements and 11
allocations across 12 updates. Reserved height alone did not prevent layout
invalidation. Feed photos and video thumbnails now use `PreviewTexture`, which
snapshots the shared immutable texture with the same centred cover crop and only
queues drawing when pixels change. Accessible image labels, descriptions,
viewport release and cache budgets remain. Thumbnail badge updates keep their
layout, and `Gtk.Video` controls are constructed on the first explicit play.
The regression test asserts zero remeasurements/allocations across portrait,
landscape and square texture arrival/eviction, while keeping the reserved size.
GTK's drawing/texture/clip contracts were checked against upstream documentation.

The maintained performance harness now has a network-free mixed-media workload;
its reports cannot be compared with the ordinary workload. Three unprofiled
250-post runs per version used the same default backend/renderer and roughly
42,253 versus 42,384 logical pixels of total scripted travel. Baseline scroll
phases recorded 1,392 frames, 19 paint spans above 25 ms and four above 50 ms
(maximum 59.4 ms); candidate phases recorded 1,395 frames, 13 above 25 ms and none
above 50 ms (maximum 32.8 ms). Individual runs varied; some baseline runs were
already similar to the candidate. These are before-paint/after-paint spans, not
GPU completion, a universal frame-rate claim or physical momentum acceptance.
Local fixture pixels also do not represent distinct-photo decoding/downloads.
Raw captures and the separate diagnostic profile remain ignored in
`build-performance/`. Lint, desktop/schema validation and the full 385-test source
suite passed on the default renderer with zero skips. Offline Flatpak build,
export and install passed (commit
`82c6f4fa91f17b69090ee3fb562ec784c06314aa11ffe988488386787786a672`).
The complete installed default-renderer suite also passed all 385 tests with zero
skips; all 56 installed Python modules matched source. Installed generated-video
preview/playback, narrow playback and disabled-thumbnail fallback captures were
visually inspected. The actual installed app's navigation smoke passed at
1280/light and 480/dark, and its image previews were visually inspected. Physical
momentum on the user's live mixed-media feed still needs user confirmation.

## Inline feed video and thumbnails — 14 November 2026

Feed videos now use the supplied Bluesky thumbnail, with the existing image
policy, viewport scheduling and bounded cache. The pinned atproto 0.0.74
`AppBskyEmbedVideo.View` optional `thumbnail` and `aspect_ratio` fields and GTK's
`Video.set_media_stream` contract were checked. No video download or pipeline
starts until explicit playback. The thumbnail becomes a native inline player
with the same reserved geometry, descriptions, sound/seek controls and explicit
retry. One player owns playback; unmap/recycling, replacement and account changes
release it. Missing, disabled and failed thumbnails retain a clear play card;
preview failures do not prevent explicit playback. Composer previews retain the
dialog player.

Lint, desktop/settings validation and offline Flatpak build/export/install passed.
The initial 380-test default-renderer source run hit two existing focus/layout
settling assertions in label popovers and distant list recycling. The expanded
X11/Cairo source suite passed 383 tests, and the installed suite passed 384 with
zero skips. After the final badge/padding refinements, all 29 video-focused native
tests passed on the default renderer against both source and installed modules;
the installed run also included an explicit thumbnail-failure fallback assertion.
Generated H.264 footage rendered and advanced through the inline widget. Installed
wide preview/playback, narrow playback and disabled-thumbnail fallback captures
were visually inspected using invented records and the installed stylesheet.
All 56 final installed Python modules matched source. The actual installed
application passed the default-renderer navigation smoke at 1280/light and
480/dark; both captures were visually inspected. Live Bluesky streams, audible
sound and human accessibility acceptance remain unverified. Cairo results are not default-renderer performance
proof.

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

## Hosted dual-architecture confirmation — 14 November 2026

[CI run 43654472987](https://github.com/nedrichards/skyloom/actions/runs/43654472987)
passed at `333aed7` on both native x86_64 and aarch64, including source checks,
build/export/install, installed/source module parity, both native test suites and
sequential demo/high-contrast/large-text captures. Flatpak and the decoder portal
ran entirely inside the official build container. Container-only D-Bus machine
state and an explicit shared runtime directory were required for the image
encoder sandbox; sandboxing remains enabled. Earlier failed hosted attempts are
retained in Actions history. This confirms hosted functional checks, not human
visual, physical-input, live-account or screen-reader acceptance.

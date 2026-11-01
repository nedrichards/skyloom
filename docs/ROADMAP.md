# Future work

The original bootstrap specification has been retired. [FEATURES.md](FEATURES.md) describes implemented behaviour; this file is the single home for outstanding product and release work. No item below implies a working feature or a published release.

## Required before public release

- Perform human acceptance with a dedicated app password entered only into the app: login, relaunch/refresh persistence, Following/pinned-feed paging, conversation/back position, like/repost/undo, nested replies, text/quote/image publication with descriptions, profile/follow/mute/block, search, notification read state and sign-out/relaunch. Mock HTTP tests do not establish live service interoperability.
- Check Orca, keyboard-only use with actual input, physical touch/pull gestures, file chooser portals, real network/cost/power transitions and laptop suspend/resume. Include compact profile/label hit areas, text selection and the pointer-to-keyboard card/control focus handoff. Native controller tests and injected clocks cover implementation contracts but not these hardware journeys. Current Xwayland synthetic input delivery is blocked; see the delivery report.
- Review at 1600 logical pixels and wider. Current captures cover 480, 800 and 1280 pixels; this desktop is only 1503 logical pixels wide. Retain light/dark/high-contrast/large-text checks.
- Configure the real public repository/homepage, then resolve AppStream's missing-homepage warning, add hosted CI, public screenshot URLs and release metadata. Review privacy/moderation messaging and bundled dependency licensing for distribution; original project work is GPLv3-or-later (see [the source sharing review](REPOSITORY_REVIEW.md)). The identity and Open Loom artwork have been selected by the maintainer; no project URL is invented. A private source upload does not complete these public-release gates.
- Build/test architecture-specific dependency sources before offering architectures beyond x86_64. Review the manifest, runtime availability and sandbox permissions before any Flathub submission. No submission, upload, tag or release is authorised by this roadmap.

## Code quality follow-up

The refactoring in [CODE_QUALITY_REVIEW.md](CODE_QUALITY_REVIEW.md#resolution) implements the review findings, including cancellation-safe storage, row/index and request ownership, Undo tokens, pager uniqueness, efficient checkpoints, media residency and strict test gates. Keep its new invariant tests in the required native gate. Obtain a clean, adequately sampled same-environment scrolling baseline before treating relative timing checks as acceptance on this shared compositor. Physical activation/keyboard/touch and live-service gates above remain outstanding.

## Rendering performance

The 60 fps target is not met for every workload. [PERFORMANCE.md](PERFORMANCE.md) records installed measurements and the safe optimisations already made. Prioritise a lighter/reusable post-cell design and allocation work for the native list buffer: 250-post views still construct roughly 200 full widget trees, causing cold-view stalls and slower dense scrolling. Preserve all retained messages, exact reading anchors, keyboard access, screen-reader semantics and one native scrolling surface. Do not conceal this by lowering the history limit, disabling animations globally or reporting only median timings. Reduce initial notification construction (86.5 ms sampled main-thread completion) and the remaining Mark seen completion work (17.3 ms). Static asynchronous presentation gaps are not a measure of blocked rendering. Recheck viewport-width transitions and idle animation activity with GTK/GSK tracing, then repeat on photo-heavy live feeds and additional hardware.

## Reliability and maintainability

- Restore reliable Xwayland injected-input delivery and obtain adequately sampled default-renderer timing runs on this shared compositor. Keep the explicit X11/Cairo functional gate separate from Wayland full-suite frame-wait failures and compositor timing limitations. Neither functional tests nor sidebar frame samples establish physical input acceptance or a frame-rate guarantee. Reduce the initial narrow-width reflow cost: the 250-post sidebar probe still takes hundreds of milliseconds before the slide can start.

- Investigate intermittent logical loader-selection/profile-focus restoration failures in standalone ConversationView fixtures, including under X11/Cairo; distinguish desktop scheduling from controller ownership before changing implementation. Also investigate the native AdwGizmo snapshot-allocation warning emitted by the rapid resize-reversal fixture. Keep these findings visible alongside passing runs; do not weaken their assertions.

- Persist more conversation/profile/notification state if a fuller offline experience is wanted. Feed pages/reading windows now have an automatically cleaned archive; conversation/profile/notification snapshots are not separately archived. There is no offline mutation queue.
- Reclaim abandoned prepared attachment copies safely, without deleting images referenced by drafts or an open composer. Current copies are retained until sign-out.
- Add translation catalogues and localise user-facing strings. British English is delivered today.
- Review upstream GI asyncio-policy and HTTPX upload deprecations as runtime/dependency updates arrive. Static typing and ShellCheck are possible additions, not currently claimed checks.
- Broader service/moderation interoperability and accessibility review may identify further changes; keep their findings here with reproducible evidence.

## Conversation follow-up acceptance

The conversation ordering redesign is implemented; see [ARCHITECTURE.md](ARCHITECTURE.md#conversation-context-and-tile-activation) and [FEATURES.md](FEATURES.md). Keep these remaining acceptance gates separate from implemented behaviour:

- Human Orca and physical keyboard/touch checks for parent/reply navigation, branch loading focus return and concise completion/error announcements.
- Wider-than-1280-pixel desktop review, alongside installed 480/800-pixel light/dark/high-contrast/large-text checks.
- Live-service review of very wide threads and server-omitted replies; the supported endpoint provides no cursor for enumerating arbitrary missing siblings. Do not promise complete conversation archives.

## Optional product work

Prioritise only when there is a complete network/model/view/error-handling slice:

- Direct messages with explicit supported app-password permissions and service routing.
- Native video playback/upload, with real codec/upload/job handling and accessible controls.
- Multiple accounts and safe account switching.
- Post deletion, bookmarks, server drafts and feed management.
- More complete moderation preferences/labeler support, including source attribution and labeller-specific definitions/preferences, and in-app reporting.

None of these optional items blocks the local preview. Revisit scope deliberately rather than retaining the old build phases as an active plan.

# Future work

## Before public release

- Test a real account using a dedicated app password entered only in the app:
  login/session restore, feed paging, conversations/Back, reactions, replies,
  text/quote/image posts with descriptions, profiles/follow/mute/block, search,
  notification read state and sign-out.
- Check Orca, physical keyboard/pointer/touch input, file portals, network and
  power changes, and suspend/resume. Include selection, focus return and branch
  loading. Review light/dark/high contrast/large text and widths above 1280 pixels.
- Supply public project metadata, screenshot URLs and hosted CI; resolve strict
  AppStream validation's missing-homepage warning. Review privacy, moderation,
  dependency licensing and sandbox permissions for distribution.
- Build and test architecture-specific dependencies before supporting more than
  x86_64. Review Flathub requirements before submission.

## Scrolling and reliability

- Resolve visual disturbance when replies or ancestors arrive during momentum
  scrolling in long conversations. Reproduce with physical input and trace the
  normal renderer; do not attribute ghosting to a renderer without evidence.
- Measure cold native-list construction, viewport geometry scans, reading
  checkpoints during sustained scrolling, item-specific widgets and notification
  completion work. Obtain matched, adequately sampled baselines before claiming
  overall performance gains. Include photo-heavy feeds and additional hardware.
- Investigate Wayland frame-wait timeouts, unreliable Xwayland input injection,
  narrow-width reflow delays and the AdwGizmo snapshot-allocation warning during
  rapid resize reversal.
- Review very wide live conversations and server-omitted replies; the endpoint
  has no cursor for enumerating arbitrary missing siblings.
- Reclaim abandoned prepared uploads without removing images used by drafts or
  an open composer.
- Add translations. Review GI asyncio-policy and HTTPX upload deprecations when
  updating dependencies.

## Optional features

Implement complete network, model, UI and recovery paths for any chosen feature:

- More offline conversation/profile/notification storage.
- Direct messages with supported permissions and service routing.
- Native video playback and upload.
- Multiple accounts and safe switching.
- Server drafts and feed management.
- Full moderation preferences, labeller attribution and in-app reporting.

This list does not authorise publishing, tagging or account mutations.

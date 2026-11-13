# AGENTS.md — maintenance instructions

Skyloom is an implemented native GNOME Bluesky client, not a bootstrap specification. Start with [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) and [docs/ROADMAP.md](docs/ROADMAP.md). Preserve useful existing work. The original build prompt and phase plans have been retired.

## Working rules

- Make reasonable implementation decisions without repeatedly asking about minor details. Preserve unrelated work and do not modify the host outside the user's authorisation.
- Build changes end to end: network, immutable model, view, state, errors and recovery. Never add inert controls, fabricated production statistics or TODO-driven user-facing features.
- GTK 4/libadwaita, GNOME HIG, Flatpak packaging and accessibility are required. No web feed or Electron shell. GNOME 51 supplies the supported Python 3.14 runtime.
- Keep GTK work on the main thread and IO/decoding on workers. Bound concurrency/cache sizes, cancel stale requests and use account generation/page liveness guards.
- Verify exact upstream API/library contracts for changed integrations. Preserve reproducible version/hash pins. Do not copy third-party code/assets without permission.
- Use the maintained SDK's dedicated app-password route, refresh persistence and libsecret. Never request, record, emit or check in main passwords, app passwords, sessions/tokens, cookies or personally identifying feed data. No plaintext token fallback.
- Honour 300 graphemes / 3000 UTF-8 bytes, UTF-8 byte-offset facets, descriptions, labels and explicit viewer mute/block state. Labelled content is visible by default with an optional in-app warning preference.
- Use shared virtualised native lists with a single content scrolling surface. Respect themes, large text, reduced motion, keyboard focus/return and screen-reader semantics.
- Preserve drafts and readable cached data on errors. Offline drafting is allowed; publishing/mutations require connection and must never be silently queued or retried.
- Keep secrets, environments, databases, sensitive logs/screenshots and disposable build outputs ignored. Fixtures/screenshots must use invented records only.

## Validation and documentation

Run `./scripts/check.sh` and checks appropriate to the change; native tests and GUI smokes run sequentially. Build/export/install and run the installed sandboxed app when the environment supports it. A host/source run or mock alone is not installed-app/live-service proof. Do not suppress failing assertions or claim unperformed human acceptance.

Update [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md) with current evidence and material limitations, [CHANGELOG.md](CHANGELOG.md) with changes, and the relevant current docs. New future work belongs in [docs/ROADMAP.md](docs/ROADMAP.md). Keep public docs clear that users supply only a dedicated app password. Publishing, tagging, creating repositories and destructive account actions require explicit task scope; a roadmap is not authorisation.

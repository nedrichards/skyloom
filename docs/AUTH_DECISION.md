# Authentication decision

Skyloom uses dedicated app-password authentication through the maintained Python AT Protocol SDK. This is the chosen production route for this application.

Create a dedicated app password in Bluesky settings and enter it directly in the native window. Never enter your main account password. Custom PDS accounts can set an HTTPS server address.

The app password is used transiently and is never saved. Refreshable sessions are stored only through libsecret. Create/import/refresh callbacks await secure persistence, and failed refresh writes must be retried before another authenticated action. No plaintext fallback is permitted. Locked/unavailable keyrings have a clear retry path.

Session creation is explicit and rate limited; sign-in retries respect the server cooldown. Normal requests use the existing session and SDK refresh handling. Sign-out clears the current identity's stored session and local account state and attempts server revocation. Offline revocation may fail; users can revoke the dedicated app password in Bluesky settings.

Tests cover sign-in, restoration, concurrent refresh, refresh persistence failures, locked keyrings, revocation, sign-out and request cooldown. An isolated dummy-entry test checks real Secret Service storage without reading an account session. Human live-account acceptance is still required; never share credentials with an agent.

References: [SDK authentication](https://atproto.blue/guides/authentication/) and [SDK client](https://atproto.blue/atproto_client/client/).

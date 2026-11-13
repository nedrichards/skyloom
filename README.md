# Skyloom

A native GNOME client for Bluesky, built with GTK 4, libadwaita and Python.
A personal project by Nick Richards, independent of Bluesky.

![Skyloom with invented demo posts](screenshots/showcase/home-1280-light.png)

The bits of Bluesky I use work fine. DMs, video upload and multiple accounts
are not included.

## Install and launch

The app targets flatpak as a build and execution environment. There is no hosted download yet.
[Build a local Flatpak bundle](docs/DEVELOPMENT.md#flatpak), then install it:

```sh
flatpak install --user dist/com.nedrichards.Skyloom-0.1.0-x86_64.flatpak
flatpak run com.nedrichards.Skyloom
```

Explore invented data without an account or network:

```sh
flatpak run com.nedrichards.Skyloom --demo
```

Demo actions stay local and do not change account preferences.

## Sign in

Create a **dedicated app password** in [Bluesky settings](https://bsky.app/settings/app-passwords).
Enter your handle and that app password in Skyloom. **Never enter your main
account password.** For another PDS, set its HTTPS address under Custom server.

Sessions are saved in your login keyring. Unlock it and retry if unavailable;
there is no plaintext fallback. Sign out in Preferences removes local account
data and the saved session. If offline, server revocation may fail; you can also
revoke the app password in Bluesky.

## Using Skyloom

- Choose a feed from the Home header. Open a post to read its conversation;
  Alt+Left returns to your reading position.
- Ctrl+N composes, Ctrl+Enter publishes and Ctrl+R refreshes. Attach up to four
  JPEG/PNG images, each with a description. Failed publishing preserves the draft;
  after a timeout, check your profile before retrying.
- New-post notifications keep your reading position. Go to top jumps to the
  newest posts; Undo restores your position. Double-click Home or use Ctrl+Home
  to fetch the newest page.
- Delete your own posts from their post menu. Deletion asks for confirmation and
  cannot be undone; a placeholder preserves the conversation and reading position.
- Save posts from their menu and find them in Bookmarks. Bookmarks are private
  and synchronise with Bluesky.
- Your post menu also opens reply and quote controls. On replies to your thread,
  hide a reply; on quotes of your posts, detach the quote. Restore these from the
  original post's controls. Hidden replies can still be opened directly.
- Preferences controls appearance, downloads and labelled-content warnings.
  Labelled content is visible by default; explicit mutes and blocks remain separate.
- Open your profile to edit its name, description and images. Select follower or
  following counts on any profile to browse people.
- Use F1 or Ctrl+? for keyboard help. Preferences and About are in the main menu.

## Privacy

No analytics or custom backend. Automatic downloads respect connection and power
policy; image downloads can be disabled in Preferences. Upload copies remove
image metadata; original files are untouched.

Drafts, prepared images and cached posts stay in private application storage,
without separate encryption. Prepared images remain until sign-out. See
[storage locations](docs/ARCHITECTURE.md#storage-locations-and-retention).

## Development and contributions

Start with [development](docs/DEVELOPMENT.md), [testing](docs/TESTING.md) and
[the roadmap](docs/ROADMAP.md). Bug reports and forks are welcome; see
[contributing](CONTRIBUTING.md) for the project's maintenance approach.

Original code, documentation and artwork are [GPL-3.0-or-later](LICENSE.md).
AppStream metadata is CC0-1.0; dependencies retain their own licences.

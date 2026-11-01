# Source sharing review

## Initial private repository — 1 November 2026

The maintainer authorised creation and upload of
[`nedrichards/skyloom`](https://github.com/nedrichards/skyloom). GitHub metadata
confirms `PRIVATE`/`isPrivate: true`. The previously empty local `.git` directory
was initialised on the host with branch `main`; no prior history or refs existed
to import. The initial source snapshot includes the current shared thread pills,
pointer-selection improvements, tests and aligned documentation.

The prospective upload contains 267 files, about 11.7 MB. The two additions since
the earlier 265-file inventory are the thread-context module and its tests.
The candidate text scan found no apparent private keys, GitHub tokens, AWS access
IDs, JWTs or literal secret assignments. Its only credential-bearing URL match
was the intentional rejected `example.invalid` fixture in `test_domain.py`.
The same 139 PNG candidates remain; chunk inspection found only image/colour
chunks, with no text, EXIF or trailing payload. No symlinks or other binary files
are in the candidate set. Earlier invented-data visual review remains the image
provenance evidence; no live account material was inspected.

Git ignore checks exclude environments, agent/cloud configuration, databases,
local caches, build repositories, bundles and the temporary publishing tools/audit
under `build-publish-review/`. No ignored file is intentionally staged. This is an
initial import, so there are no historical commits containing previously removed
files. Pattern scans and provenance review reduce risk but are not a guarantee
against every possible secret format.

Current validation is recorded in DELIVERY_REPORT.md: 218 source and 218
installed-code tests passed, plus the installed conversation GUI scenario. The
publication-time `check.sh` rerun passed static checks and again stopped at the
nested Flatpak instance allocation; application code has not changed since the
passing installed validation. Public distribution, human account/Orca/physical
input acceptance and performance gates remain separate. No tag or release is
part of this private upload.

## Historical pre-upload review — 28 October 2026

The current source tree was reviewed for an initial private GitHub upload. No
repository, commit, remote, tag or release was created by this review.

## Scope and result

No apparent local credentials or personal home-directory paths were found in
the candidate text files. The review covered source, tests, scripts, dependency
locks, packaging, fixtures, documentation and image assets. Public maintainer
credit (Nick Richards), the application ID and public upstream service/package
URLs are intentional project information.

Git reports that this directory is not a repository, both locally and through
the host. The visible `.git` directory is empty. Therefore **existing commits,
refs, remotes and staged files could not be inspected or certified**. A temporary
Git repository outside the source tree was used with this tree as its worktree
to enumerate files using the actual `.gitignore` rules. This checks prospective
initial-upload contents, not historical contents. If a repository with history
is supplied later, inspect its index and all refs before uploading it; ignoring
a file does not remove an already tracked file or its history.

The final prospective inventory contains 265 files, including this report.
Before the documentation additions it contained 262 files; all original source
and test files remain eligible. New files are this report, `LICENSE.md` and
`CONTRIBUTING.md`.

## Evidence

- Pattern searches covered private keys, GitHub credentials, AWS access IDs,
  encoded JWTs, credential-bearing URLs, literal secret assignments, app-password
  shapes, email addresses and personal home paths. The sole URL/email-shaped
  match was the invented user/password URL on `example.invalid` in `test_urls`,
  which is intentionally rejected. Authentication tests generate unsigned synthetic tokens
  and use explicitly invalid passwords. No real session/keyring or account data
  was opened. Pattern searches are evidence, not a guarantee against every
  possible secret format.
- All 139 binary candidates are PNGs: original artwork, generated fixtures and
  demo captures. Their contact sheet was visually reviewed. PNG metadata and
  chunk inspection found image/colour information only, with no text, EXIF,
  location metadata or trailing payload. The screenshot runner requires explicit
  demo mode; fixtures use invented identities and reserved example domains.
- Ignore rules exclude local environments, build/export repositories, wheels,
  databases and sidecars, logs, environment files, local credential/configuration
  directories, keys, sessions, editor state and local notes. Screenshots are
  restricted to PNGs in the two reviewed invented-data directories. Those
  directories must continue to contain invented records only.
- Git's own `check-ignore` verified 35 local/sensitive example paths were excluded
  and 12 source/documentation/demo example paths remained visible. Comparing
  candidate inventories confirmed no original source was accidentally hidden.
  Future authentication modules remain visible: broad `*secret*`/`*token*`
  filename exclusions were replaced with more specific local-file rules.
- Session storage remains libsecret-only, with sanitised errors and disabled
  third-party request diagnostics. No plaintext credential fallback was added.
  The manifest retains narrow Secret Service access and no home-directory grant.

## Licence and reader documentation

`COPYING` already contains the complete GNU GPL version 3. The README, package
metadata, AppStream project licence and source package notice now consistently
state `GPL-3.0-or-later`. `LICENSE.md` explicitly applies that grant to original
code, documentation, fixtures and artwork; AppStream metadata keeps its declared
CC0-1.0 exception and dependencies retain their own licences. The About dialog
already uses GTK's GPLv3-or-later licence value.

The README now links the licence and contribution policy, explains the personal
project/sharing focus and directs readers to build a local bundle before trying
to install it. `CONTRIBUTING.md` welcomes forks, reports and contributions while
setting realistic expectations for maintenance and review. Dedicated app-password
instructions, preview status and outstanding human/live-service gates remain
prominent. No fictional repository URL or download was added.

## Validation and remaining limits

Pinned Ruff stable/selected preview checks, formatting, Python compilation,
shell syntax, desktop-file validation and strict settings-schema validation
passed through `scripts/check.sh` before its runtime launch failed with
“Unable to allocate instance id” in this nested environment. A direct host-side
invocation of the same source runtime suite then passed **204 tests, zero skips**
against the installed Flatpak dependencies. A later attempt to route the complete
script through the host and an installed demo smoke attempt were blocked by
desktop-bus access (“Operation not permitted”); neither is claimed as a pass.
Project TOML licence/file declarations and local Markdown file links were also
checked.

This change affects ignore rules, metadata and documentation; application code
and the installed package were not changed or rebuilt. Prior installed-app,
bundle and GUI evidence remains historical evidence in the delivery report.
Human account acceptance, Orca/physical input and performance limitations remain
in the roadmap. Source sharing readiness is separate from release acceptance.

Before uploading a subsequently initialised or restored repository, inspect its
actual `git status --short --ignored`, `git ls-files` and
`git diff --cached --name-status`; scan the selected contents and all existing
history. Recheck any new screenshots. Keep generated outputs and account material
out of the index even for a private repository.

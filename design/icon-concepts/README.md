# Skyloom — Open Loom

The maintainer selected **Open Loom** and authorised its refinement and rollout. The full-colour and symbolic production sources are now:

- [`../../data/icons/com.nedrichards.Skyloom.svg`](../../data/icons/com.nedrichards.Skyloom.svg)
- [`../../data/icons/com.nedrichards.Skyloom-symbolic.svg`](../../data/icons/com.nedrichards.Skyloom-symbolic.svg)

The chosen metaphor is a physical wooden loom weaving separate pale threads into sky-blue cloth: individual voices forming a conversation. The maple frame gives Skyloom a warm, distinctive silhouette among blue social apps.

Refinement retained the selected design while aligning the wood-beam profiles and highlights, giving the blue weft bands a restrained lower edge, and simplifying the symbolic weave onto crisp two-pixel geometry. Broad over-under crossings remain readable at small sizes. Gradients are restricted to the rounded wooden beams; the cloth uses flat planes. The silhouette rests at the GNOME baseline with no external drop shadow. This follows the current [GNOME app-icon guidance](https://developer.gnome.org/hig/guidelines/app-icons.html).

[**open-loom-final.png**](open-loom-final.png) shows the final artwork on light and dark backgrounds, plus actual 32/64/128 pixel colour and 16/32/64 pixel symbolic checks. `previews/` contains seven transparent PNG renders. The production SVGs are self-contained editable vectors with no embedded raster, text artwork, external references or third-party assets.

All rejected Cloud Chorus and Signal Kite artwork, rejected symbolics, the three-way contact sheet and superseded Open Loom preview files have been removed. This directory retains only the final selected identity's QA artefacts and renderer; the production SVGs above are the canonical sources.

## Verification and reproduction

Both production SVGs were parsed and rendered with the GNOME 51 SDK's librsvg. The final light/dark sheet and small-size colour/symbolic previews were visually inspected. The renderer passes the project's pinned Ruff lint, selected preview rules and formatter. The final application package installs both canonical SVGs; installed file hashes match these sources and the installed demo welcome screen was inspected with the new icon in standard and high-contrast/large-text runs. This does not claim human screen-reader review.

```sh
flatpak run --user --devel --command=python3 \
  --filesystem="$PWD/design/icon-concepts" \
  --filesystem="$PWD/data/icons:ro" com.nedrichards.Skyloom \
  "$PWD/design/icon-concepts/render.py"
```

In the agent's nested environment, prefix that command with `flatpak-spawn --host`. No new runtime dependency or host package is needed. Original project artwork, GPL-3.0-or-later.

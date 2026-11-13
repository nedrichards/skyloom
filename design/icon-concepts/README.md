# Icon previews

Edit the full-colour and symbolic SVGs in [`data/icons/`](../../data/icons/).
To regenerate local previews and the light/dark size sheet:

```sh
flatpak run --user --devel --command=python3 \
  --filesystem="$PWD/design/icon-concepts" \
  --filesystem="$PWD/data/icons:ro" com.nedrichards.Skyloom \
  "$PWD/design/icon-concepts/render.py"
```

Generated PNGs are ignored. Review small sizes on light and dark backgrounds
when changing the artwork.

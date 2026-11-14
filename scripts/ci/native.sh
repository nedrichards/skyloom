#!/usr/bin/env bash
# Run in a disposable CI checkout after installing its bundle, inside a display session.
set -euo pipefail
tooling=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
mkdir -p build-ci
backend=${BUILD_BACKEND:-x11}
display_args=(--socket=x11 --nosocket=wayland --env=GDK_BACKEND=x11 --env=GSK_RENDERER=cairo)
if [[ "$backend" == wayland ]]; then
    display_args=(--socket=wayland --nosocket=x11 --env=GDK_BACKEND=wayland)
fi
app=com.nedrichards.Skyloom
runtime=(flatpak run --user "${display_args[@]}" --env=SKYLOOM_PROPERTY_CASES="${SKYLOOM_PROPERTY_CASES:-50}" --command=python3 --filesystem="$PWD:ro" --filesystem="$tooling:ro" --filesystem="$PWD/build-ci")
"${runtime[@]}" --env=PYTHONPATH=/app/share/skyloom "$app" "$tooling/scripts/ci/installed.py" "$PWD" "$BUILD_ARCH"
"${runtime[@]}" "$app" - <<'PY'
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
pixels = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 4, 4)
pixels.fill(0x224466ff)
ok, payload = pixels.save_to_bufferv("png", [], [])
if not ok or not payload.startswith(b"\x89PNG"):
    raise RuntimeError("Sandboxed PNG encoder preflight failed")
print("DECODER_SANDBOX_PREFLIGHT_PASS: generated PNG encoded with sandbox enabled")
PY
# Source and installed modules are tested separately; GUI processes never overlap tests.
"${runtime[@]}" --env=PYTHONPATH="$PWD/src" "$app" "$tooling/scripts/runtime-tests.py" --tests "$PWD/tests" --report "$PWD/build-ci/source-tests.json"
"${runtime[@]}" --env=PYTHONPATH=/app/share/skyloom "$app" "$tooling/scripts/runtime-tests.py" --tests "$PWD/tests" --report "$PWD/build-ci/installed-tests.json"
if [[ ${SDK_PROBE:-false} == true ]]; then
    # Only the SDK pin is relaxed; all other production pins remain constraints.
    sed '/^atproto==/d' requirements.lock > build-ci/sdk-constraints.txt
    # pip belongs to the SDK, not the production Platform. Install into a
    # disposable directory, then import the result in the installed application.
    sdk=(flatpak run --system --share=network --command=python3 --filesystem="$PWD/build-ci" --env=PIP_NO_CACHE_DIR=1 --env=PIP_DISABLE_PIP_VERSION_CHECK=1 org.gnome.Sdk//51)
    "${sdk[@]}" -m pip install --only-binary=:all: --target "$PWD/build-ci/sdk" \
        --constraint "$PWD/build-ci/sdk-constraints.txt" --upgrade atproto
    "${sdk[@]}" -m pip freeze --path "$PWD/build-ci/sdk" > build-ci/sdk-resolved.txt
    "${runtime[@]}" --env=PYTHONPATH="$PWD/build-ci/sdk:/app/share/skyloom" "$app" "$tooling/scripts/runtime-tests.py" --tests "$PWD/tests" --report "$PWD/build-ci/sdk-tests.json"
fi
for variant in standard high-contrast large-text; do
    extra=()
    [[ "$variant" != high-contrast ]] || extra+=(--env=ADW_DEBUG_HIGH_CONTRAST=1)
    [[ "$variant" != large-text ]] || extra+=(--env=SKYLOOM_SMOKE_FONT="Adwaita Sans 16")
    output="$PWD/build-ci/visual/$variant"
    mkdir -p "$output"
    if [[ "$variant" == high-contrast ]]; then
        flatpak run --user "${display_args[@]}" "${extra[@]}" --command=python3 "$app" - <<'PY'
import gi
gi.require_version("Adw", "1")
from gi.repository import Adw
Adw.init()
if not Adw.StyleManager.get_default().get_high_contrast():
    raise RuntimeError("High-contrast smoke requires active high-contrast styling")
print("HIGH_CONTRAST_PASS: libadwaita high-contrast styling is active")
PY
    fi
    # The full standard smoke exercises all existing scenarios; the variants
    # exercise navigation at both 1280/light and 480/dark without duplicating it.
    scenario=navigation
    [[ "$variant" != standard ]] || scenario=full
    timeout 600 flatpak run --user "${display_args[@]}" "${extra[@]}" --filesystem="$output" \
        "$app" --demo --smoke-test "$output" --smoke-scenario "$scenario"
done

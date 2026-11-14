#!/usr/bin/env bash
set -euo pipefail
tooling=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
pids=()
cleanup() {
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
if [[ ${BUILD_BACKEND:-x11} == x11 ]]; then
    export XDG_DATA_DIRS="$tooling/build-ci/display-tools/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
    export XDG_CONFIG_DIRS="$tooling/build-ci/display-tools/etc/xdg:${XDG_CONFIG_DIRS:-/etc/xdg}"
    openbox --sm-disable >build-ci/window-manager.log 2>&1 &
    pids+=("$!")
    xcompmgr >build-ci/compositor.log 2>&1 &
    pids+=("$!")
    sleep 1
    for pid in "${pids[@]}"; do kill -0 "$pid"; done
elif [[ "$BUILD_BACKEND" == wayland ]]; then
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    mkdir -p "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"
    export WAYLAND_DISPLAY=skyloom-ci
    weston --no-config --backend=headless --renderer=pixman --width=1920 --height=1200 \
        --socket="$WAYLAND_DISPLAY" --idle-time=0 >build-ci/compositor.log 2>&1 &
    pids+=("$!")
    for _ in {1..50}; do
        [[ ! -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]] || break
        kill -0 "${pids[0]}"
        sleep 0.1
    done
    test -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"
else
    echo 'Unsupported display backend' >&2
    exit 2
fi
bash "$tooling/scripts/ci/native.sh"

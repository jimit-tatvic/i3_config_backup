#!/usr/bin/env bash
# /* ---- 💫 Night Light Toggle (Redshift for X11) 💫 ---- */
set -euo pipefail

export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" ]]; then
    if [[ -f "/run/user/$(id -u)/gdm/Xauthority" ]]; then
        export XAUTHORITY="/run/user/$(id -u)/gdm/Xauthority"
    elif [[ -f "$HOME/.Xauthority" ]]; then
        export XAUTHORITY="$HOME/.Xauthority"
    fi
fi

STATE_FILE="${XDG_RUNTIME_DIR:-/tmp}/nightlight_state"
ACTION="${1:-toggle}"

update_polybar() {
    local target_hook="$1"
    polybar-msg action "#nightlight.hook.${target_hook}" >/dev/null 2>&1 || true
}

is_enabled() {
    if [ -f "$STATE_FILE" ]; then
        [ "$(cat "$STATE_FILE" 2>/dev/null)" = "1" ] && return 0 || return 1
    fi
    local gamma
    gamma=$(xrandr --verbose 2>/dev/null | grep -m1 "Gamma:" | awk '{print $2}' || echo "1.0:1.0:1.0")
    if [ -n "$gamma" ] && [ "$gamma" != "1.0:1.0:1.0" ]; then
        return 0
    fi
    return 1
}

enable_nightlight() {
    pkill -x redshift 2>/dev/null || true
    if command -v redshift >/dev/null 2>&1; then
        redshift -m randr -P -O 4500 >/dev/null 2>&1
    fi
    echo "1" > "$STATE_FILE"
    update_polybar 1
    notify-send -t 1500 -a "Night Light" -i night-light-symbolic "Night Light" "Enabled (4500K Warm)" 2>/dev/null || true
}

disable_nightlight() {
    pkill -x redshift 2>/dev/null || true
    if command -v redshift >/dev/null 2>&1; then
        redshift -m randr -x >/dev/null 2>&1 || true
    fi
    echo "0" > "$STATE_FILE"
    update_polybar 0
    notify-send -t 1500 -a "Night Light" -i night-light-disabled-symbolic "Night Light" "Disabled (Day mode)" 2>/dev/null || true
}

case "$ACTION" in
    "on"|"enable")
        enable_nightlight
        ;;
    "off"|"disable")
        disable_nightlight
        ;;
    "toggle")
        if is_enabled; then
            disable_nightlight
        else
            enable_nightlight
        fi
        ;;
    "restore"|"sync")
        if is_enabled; then
            pkill -x redshift 2>/dev/null || true
            redshift -m randr -P -O 4500 >/dev/null 2>&1 || true
            update_polybar 1
        else
            redshift -m randr -x >/dev/null 2>&1 || true
            update_polybar 0
        fi
        ;;
    "status")
        if is_enabled; then
            echo "on"
        else
            echo "off"
        fi
        ;;
    *)
        echo "Usage: $0 [toggle|on|off|restore|sync|status]"
        exit 1
        ;;
esac

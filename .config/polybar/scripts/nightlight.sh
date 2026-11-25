#!/usr/bin/env bash
# Polybar Nightlight Status Script
set -euo pipefail

STATE_FILE="${XDG_RUNTIME_DIR:-/tmp}/nightlight_state"

if [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE" 2>/dev/null)" = "1" ]; then
    echo "󰖔 Night"
else
    gamma=$(xrandr --verbose 2>/dev/null | grep -m1 "Gamma:" | awk '{print $2}' || echo "1.0:1.0:1.0")
    if [ -n "$gamma" ] && [ "$gamma" != "1.0:1.0:1.0" ]; then
        echo "󰖔 Night"
    else
        echo "󰖙 Day"
    fi
fi

#!/usr/bin/env bash
# ==============================================================================
#  Polybar Weather Script (wttr.in)
# ==============================================================================
set -euo pipefail

CACHE_FILE="/tmp/polybar_weather_cache"
CACHE_AGE=900 # 15 minutes

is_valid_output() {
    local text="$1"
    if [[ -z "$text" ]]; then
        return 1
    fi
    # Reject any HTML tags, error codes, or excessively long payloads
    if [[ "$text" =~ \<|\>|html|head|body|meta|script|unknown|error|404|500|redirect ]]; then
        return 1
    fi
    if [ "${#text}" -gt 25 ]; then
        return 1
    fi
    return 0
}

is_valid_cache() {
    if [ ! -f "$CACHE_FILE" ]; then
        return 1
    fi
    local cached
    cached=$(head -n 1 "$CACHE_FILE" 2>/dev/null || true)
    is_valid_output "$cached"
}

get_weather() {
    local raw=""
    # 1. Try https://wttr.in over HTTPS with strict timeout
    raw=$(curl -s -f --connect-timeout 4 --max-time 6 "https://wttr.in?format=%C|%t" 2>/dev/null || true)

    # 2. Fallback to https://wttr.is if wttr.in timed out or returned errors
    if [[ -z "$raw" || "$raw" =~ \<|\>|html|error ]]; then
        raw=$(curl -s -f --connect-timeout 4 --max-time 6 "https://wttr.is?format=%C|%t" 2>/dev/null || true)
    fi

    # 3. Validate response format: must have '|' delimiter and no HTML tags
    if [[ -n "$raw" && "$raw" == *"|"* ]] && is_valid_output "$raw"; then
        local condition="${raw%%|*}"
        local temp="${raw##*|}"

        # Clean condition and temperature
        condition=$(echo "$condition" | xargs)
        temp=$(echo "$temp" | grep -o -E '^[+-]?[0-9]+(°C|°F|C|F)?' || echo "")

        # If temperature is valid
        if [[ -n "$temp" ]]; then
            # Night detection (7 PM to 6 AM)
            local hour
            hour=$(date +%H)
            local icon="󰖙"
            local cond_lower
            cond_lower=$(echo "$condition" | tr '[:upper:]' '[:lower:]')

            case "$cond_lower" in
                *thunder*|*storm*|*lightning*) icon="󰙾" ;;
                *rain*|*drizzle*|*shower*)    icon="󰖗" ;;
                *snow*|*blizzard*|*sleet*|*ice*) icon="󰖘" ;;
                *fog*|*mist*|*haze*)          icon="󰖑" ;;
                *cloud*|*overcast*)           icon="󰖐" ;;
                *partly*)                     icon="󰖕" ;;
                *clear*)
                    if [ "$hour" -ge 19 ] || [ "$hour" -lt 6 ]; then
                        icon="󰖔"
                    else
                        icon="󰖙"
                    fi
                    ;;
                *sunny*)                      icon="󰖙" ;;
                *)                            icon="󰖙" ;;
            esac

            local output="$icon $temp"
            echo "$output" > "$CACHE_FILE"
            echo "$output"
            return 0
        fi
    fi

    # 4. If fetch failed or invalid, fall back to valid cache or clean N/A
    if is_valid_cache; then
        cat "$CACHE_FILE"
    else
        echo "󰖙 N/A"
    fi
}

# Purge corrupted cache file if present
if [ -f "$CACHE_FILE" ] && ! is_valid_cache; then
    rm -f "$CACHE_FILE"
fi

# If force flag passed, ignore cache
if [[ "${1:-}" != "force" && -f "$CACHE_FILE" ]]; then
    file_age=$(( $(date +%s) - $(stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0) ))
    if [ "$file_age" -lt "$CACHE_AGE" ]; then
        cat "$CACHE_FILE"
        exit 0
    fi
fi

get_weather

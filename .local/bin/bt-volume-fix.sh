#!/bin/bash
# Auto-fix Bluetooth AVRCP hardware volume to max on connect
# Fix: only set the BT hardware transport volume, NOT the system sink volume

pactl subscribe 2>/dev/null | grep --line-buffered "new.*sink\|change.*sink" | while read -r event; do
    sleep 1
    # Find active bluetooth transport and set hardware volume to max
    transport=$(echo "menu transport
list" | bluetoothctl 2>/dev/null | grep "Transport" | awk '{print $2}')

    if [ -n "$transport" ]; then
        # Set only the Bluetooth hardware transport volume (0-127), not system volume
        echo "menu transport
volume $transport 127" | bluetoothctl &>/dev/null
    fi
done

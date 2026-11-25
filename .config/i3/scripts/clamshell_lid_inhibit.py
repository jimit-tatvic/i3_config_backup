#!/usr/bin/env python3
"""
Clamshell & Display Hotplug Manager for i3
------------------------------------------
1. Automatically manages systemd lid switch inhibition when external displays are connected.
2. Automatically detects HDMI hotplug (connect/disconnect) with settling debounce,
   seamlessly applying the correct profile (Office vs Home vs Laptop-only).
"""

import glob
import os
import signal
import subprocess
import sys
import time

LOCK_PROCESS = None

def has_external_display():
    for status_path in glob.glob('/sys/class/drm/card*-*/status'):
        if 'eDP' in status_path or 'LVDS' in status_path:
            continue
        try:
            with open(status_path, 'r') as f:
                if f.read().strip() == 'connected':
                    return True
        except Exception:
            pass
    return False

def acquire_inhibit():
    global LOCK_PROCESS
    if LOCK_PROCESS is None or LOCK_PROCESS.poll() is not None:
        try:
            LOCK_PROCESS = subprocess.Popen([
                "systemd-inhibit",
                "--what=handle-lid-switch",
                "--who=ClamshellInhibitor",
                "--why=External display (HDMI) is connected",
                "--mode=block",
                "sleep", "infinity"
            ])
            print("[+] Acquired lid switch inhibitor (HDMI connected).")
        except Exception as e:
            print(f"[-] Failed to acquire inhibitor: {e}", file=sys.stderr)

def release_inhibit():
    global LOCK_PROCESS
    if LOCK_PROCESS is not None:
        if LOCK_PROCESS.poll() is None:
            LOCK_PROCESS.terminate()
            try:
                LOCK_PROCESS.wait(timeout=2)
            except subprocess.TimeoutExpired:
                LOCK_PROCESS.kill()
        LOCK_PROCESS = None
        print("[-] Released lid switch inhibitor (external display disconnected).")

def apply_display_profile():
    # Settling delay: allow DDC / EDID I2C lines to complete handshake
    time.sleep(0.7)
    try:
        env = dict(os.environ)
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
        if "XAUTHORITY" not in env:
            env["XAUTHORITY"] = os.path.expanduser(f"/run/user/{os.getuid()}/gdm/Xauthority")
            if not os.path.exists(env["XAUTHORITY"]):
                env["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")

        res = subprocess.run(
            ["autorandr", "--change"],
            check=False,
            capture_output=True,
            text=True,
            env=env
        )
        print(f"[*] autorandr --change executed: {res.stdout.strip() or res.stderr.strip()}")
    except Exception as e:
        print(f"[-] Failed to run autorandr: {e}", file=sys.stderr)

def cleanup(signum=None, frame=None):
    release_inhibit()
    sys.exit(0)

def main():
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    print("[*] Clamshell & Display Hotplug Manager started.")

    last_state = has_external_display()
    if last_state:
        acquire_inhibit()

    while True:
        try:
            connected = has_external_display()
            if connected != last_state:
                last_state = connected
                if connected:
                    print("[*] External display connected detected.")
                    acquire_inhibit()
                    apply_display_profile()
                else:
                    print("[*] External display disconnect detected.")
                    release_inhibit()
                    apply_display_profile()
        except Exception as e:
            print(f"[-] Error in monitor loop: {e}", file=sys.stderr)

        time.sleep(1)

if __name__ == '__main__':
    main()

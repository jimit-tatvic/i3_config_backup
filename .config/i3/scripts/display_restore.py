#!/usr/bin/env python3
"""
i3 Dual-Monitor Display State Tracker & Restorer
------------------------------------------------
Saves workspace & window placements while dual monitors are connected,
and restores all workspaces and windows back to their designated displays
and workspaces whenever HDMI is reconnected.
"""

import os
import sys
import json
import time
import socket
import struct
import subprocess
import signal

STATE_FILE = os.path.expanduser("~/.cache/i3_dual_display_state.json")
PID_FILE = os.path.expanduser(f"/run/user/{os.getuid()}/i3_display_tracker.pid")

# i3 IPC Protocol Constants
I3_MAGIC = b"i3-ipc"
CMD_RUN_COMMAND = 0
CMD_GET_WORKSPACES = 1
CMD_SUBSCRIBE = 2
CMD_GET_OUTPUTS = 3
CMD_GET_TREE = 4

def get_socket_path():
    sock = os.environ.get("I3SOCK")
    if sock and os.path.exists(sock):
        return sock
    try:
        out = subprocess.check_output(["i3", "--get-socketpath"], stderr=subprocess.DEVNULL)
        path = out.decode("utf-8").strip()
        if os.path.exists(path):
            return path
    except Exception:
        pass
    
    uid = os.getuid()
    candidates = [
        f"/run/user/{uid}/i3/ipc-socket.*",
        f"/tmp/i3-{os.environ.get('USER', 'jimitchavda')}/ipc-socket.*"
    ]
    import glob
    for pat in candidates:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return None

def i3_query(cmd_type, payload=""):
    sock_path = get_socket_path()
    if not sock_path:
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(sock_path)
        p_bytes = payload.encode("utf-8")
        s.sendall(I3_MAGIC + struct.pack("<II", len(p_bytes), cmd_type) + p_bytes)
        
        header = s.recv(14)
        if len(header) < 14:
            s.close()
            return None
        length, _ = struct.unpack("<II", header[6:14])
        data = b""
        while len(data) < length:
            chunk = s.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        s.close()
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        return None

def run_i3_cmd(command):
    res = i3_query(CMD_RUN_COMMAND, command)
    return res

def extract_windows(node, ws=None, out=None):
    res = {}
    if node.get("type") == "output":
        out = node.get("name")
    elif node.get("type") == "workspace":
        ws = node.get("name")
        
    w_id = node.get("window")
    w_class = node.get("window_properties", {}).get("class", "")
    
    # Filter out docks/panels like Polybar or i3bar
    if w_id and ws and w_class not in ["Polybar", "i3bar", "Dunst", "scratchpad"]:
        res[str(w_id)] = {
            "workspace": ws,
            "output": out,
            "class": w_class,
            "instance": node.get("window_properties", {}).get("instance", ""),
            "name": node.get("name", "")
        }
    for c in node.get("nodes", []) + node.get("floating_nodes", []):
        res.update(extract_windows(c, ws, out))
    return res

def save_state():
    outputs = i3_query(CMD_GET_OUTPUTS)
    if not outputs:
        return False
        
    active_outs = [o for o in outputs if o.get("active")]
    if len(active_outs) < 2:
        # Do NOT overwrite dual monitor state when only single display is connected!
        return False
        
    primary = next((o["name"] for o in active_outs if o.get("primary")), active_outs[0]["name"])
    external = next((o["name"] for o in active_outs if o["name"] != primary), None)
    if not external:
        return False
        
    workspaces = i3_query(CMD_GET_WORKSPACES) or []
    tree = i3_query(CMD_GET_TREE) or {}
    
    ws_map = {w["name"]: w["output"] for w in workspaces}
    visible = {w["output"]: w["name"] for w in workspaces if w.get("visible")}
    focused = next((w["name"] for w in workspaces if w.get("focused")), None)
    
    windows = extract_windows(tree)
    
    state = {
        "timestamp": int(time.time()),
        "primary_output": primary,
        "external_output": external,
        "workspaces": ws_map,
        "windows": windows,
        "visible": visible,
        "focused": focused
    }
    
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp_file = f"{STATE_FILE}.tmp"
    with open(tmp_file, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_file, STATE_FILE)
    return True

def restore_state():
    outputs = i3_query(CMD_GET_OUTPUTS)
    if not outputs:
        print("[!] Failed to query i3 outputs.")
        return False
        
    active_outs = [o for o in outputs if o.get("active")]
    if len(active_outs) < 2:
        print("[i] Single display active. Nothing to restore for secondary monitor.")
        return False
        
    primary = next((o["name"] for o in active_outs if o.get("primary")), active_outs[0]["name"])
    external = next((o["name"] for o in active_outs if o["name"] != primary), None)
    if not external:
        return False
        
    if not os.path.exists(STATE_FILE):
        print(f"[!] State file {STATE_FILE} not found.")
        return False
        
    try:
        with open(STATE_FILE, "r") as f:
            saved = json.load(f)
    except Exception as e:
        print(f"[!] Failed to read state file: {e}")
        return False

    saved_ext = saved.get("external_output")
    saved_workspaces = saved.get("workspaces", {})
    saved_windows = saved.get("windows", {})
    saved_visible = saved.get("visible", {})
    saved_focused = saved.get("focused")

    print(f"[*] Restoring state for dual monitors ({primary} + {external})...")
    
    # 1. Relocate workspaces that were on the external display
    cmds = []
    for ws, out in saved_workspaces.items():
        if out == saved_ext:
            cmds.append(f'workspace "{ws}", move workspace to output "{external}"')
    if cmds:
        run_i3_cmd("; ".join(cmds))
        time.sleep(0.05) # Brief pause for i3 geometry recalculation

    # 2. Relocate windows back to their previous workspaces
    curr_tree = i3_query(CMD_GET_TREE) or {}
    curr_windows = extract_windows(curr_tree)
    
    win_cmds = []
    restored_wins = 0
    for wid, cur_info in curr_windows.items():
        if wid in saved_windows:
            target_ws = saved_windows[wid].get("workspace")
            if target_ws and cur_info.get("workspace") != target_ws:
                win_cmds.append(f'[id="{wid}"] move container to workspace "{target_ws}"')
                restored_wins += 1
                
    if win_cmds:
        run_i3_cmd("; ".join(win_cmds))
        print(f"[*] Repositioned {restored_wins} windows into their original workspaces.")

    # 3. Restore visible & focused workspaces
    view_cmds = []
    if saved_visible.get(saved_ext):
        view_cmds.append(f'workspace "{saved_visible[saved_ext]}"')
    if saved_visible.get(saved.get("primary_output")):
        view_cmds.append(f'workspace "{saved_visible[saved["primary_output"]]}"')
    if saved_focused:
        view_cmds.append(f'workspace "{saved_focused}"')
    if view_cmds:
        run_i3_cmd("; ".join(view_cmds))

    print("[SUCCESS] All workspaces and windows restored!")
    try:
        subprocess.run([
            "notify-send", "-i", os.path.expanduser("~/.config/swaync/images/ja.png"),
            "Display", f"Restored workspaces & windows to {external}"
        ], check=False, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    return True

def daemon_loop():
    # Enforce singleton daemon
    pid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as pf:
                old_pid = int(pf.read().strip())
            os.kill(old_pid, 0)
            print(f"Display tracker daemon already running (PID {old_pid}). Exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
            
    with open(PID_FILE, "w") as pf:
        pf.write(str(pid))

    def cleanup(signum, frame):
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    print(f"[*] Display tracker daemon started (PID {pid}).")
    save_state()

    while True:
        sock_path = get_socket_path()
        if not sock_path:
            time.sleep(2)
            continue
            
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(sock_path)
            
            # Subscribe to workspace and window events
            sub_payload = json.dumps(["workspace", "window"]).encode("utf-8")
            s.sendall(I3_MAGIC + struct.pack("<II", len(sub_payload), CMD_SUBSCRIBE) + sub_payload)
            
            # Read subscription response
            h = s.recv(14)
            l, _ = struct.unpack("<II", h[6:14])
            s.recv(l)
            
            last_save = 0
            while True:
                header = s.recv(14)
                if len(header) < 14:
                    break
                length, _ = struct.unpack("<II", header[6:14])
                ev_data = b""
                while len(ev_data) < length:
                    c = s.recv(length - len(ev_data))
                    if not c:
                        break
                    ev_data += c
                    
                now = time.time()
                # Debounce writes to disk (1.5 second cooldown)
                if now - last_save >= 1.5:
                    if save_state():
                        last_save = now
            s.close()
        except Exception:
            time.sleep(2)

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "--save"
    if action == "--restore":
        restore_state()
    elif action == "--daemon":
        daemon_loop()
    elif action == "--save":
        if save_state():
            print(f"[SUCCESS] Current dual-monitor layout saved to {STATE_FILE}")
        else:
            print("[i] External display not active; existing dual-monitor layout preserved.")
    else:
        print("Usage: display_restore.py [--save | --restore | --daemon]")

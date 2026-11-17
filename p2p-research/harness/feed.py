#!/usr/bin/env python3
"""Host-side credential feeder for the GQ harness (runs on the Mac).

Fetches the camera's getP2PInfo from the author' own AC Infinity cloud account
in-process and hands {did, intstr, key} to the harness app over an
adb-forwarded loopback socket. Credential values are never printed, never
written to disk, and never logged -- only HTTP codes and field lengths.
"""
import json
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.acinfinityserver.com"
TOKEN_FILE = "/Users/YOURNAME/.config/aci/token.json"
ADB = "/opt/homebrew/bin/adb"
SERIAL = "emulator-5554"
PORT = 18777


def post(path, tok, form=None):
    body = b""
    headers = {"token": tok}
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=body, method="POST",
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


def find_camera_devid(node):
    if isinstance(node, dict):
        if node.get("devType") == 10001 and node.get("devId"):
            return str(node["devId"])
        for v in node.values():
            hit = find_camera_devid(v)
            if hit:
                return hit
    elif isinstance(node, list):
        for v in node:
            hit = find_camera_devid(v)
            if hit:
                return hit
    return None


def main():
    tok = json.load(open(TOKEN_FILE))["user_id"]
    code, devs = post("/api/user/devInfoListAll", tok, form={"userId": tok})
    print("devInfoListAll http", code)
    cam = find_camera_devid(devs)
    if not cam:
        print("camera devId not found")
        return 1
    code, info = post("/api/ipc/getP2PInfo?devId=" + cam, tok)
    print("getP2PInfo http", code)
    data = info.get("data", info) if isinstance(info, dict) else {}
    payload = {k: str(data.get(k, "")) for k in ("did", "intstr", "key")}
    for k, v in payload.items():
        print("field", k, "len", len(v))
    if not all(payload.values()):
        print("missing fields")
        return 1

    subprocess.run([ADB, "-s", SERIAL, "forward", f"tcp:{PORT}", f"tcp:{PORT}"],
                   check=True, capture_output=True)
    line = (json.dumps(payload) + "\n").encode()
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=5) as s:
                s.sendall(line)
            print("fed credentials to harness over loopback")
            return 0
        except OSError:
            time.sleep(2)
    print("harness never listened")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Spectron PPPP dig, stage 2 (read-only): HELLO reachability check, then a
full cs2pppp session attempt (relay-preferred). Prints the session's own
protocol log as evidence. Credentials stay in process memory.
"""
import json
import re
import socket
import struct
import sys
import time
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
from stage1 import fetch_p2p, find_sbox, brute_lut, SO  # noqa: E402

DIR_PORT = 32100


def hello_test(servers):
    """MSG_HELLO (0x00) to each directory server; expect HELLO_ACK (0x01)."""
    pkt = struct.pack(">BBH", 0xF1, 0x00, 0)
    for ip in servers:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3.0)
        try:
            s.sendto(pkt, (ip, DIR_PORT))
            data, addr = s.recvfrom(4096)
            ok = len(data) >= 2 and data[0] == 0xF1
            print(f"HELLO {ip}: reply {len(data)}B from {addr} "
                  f"type=0x{data[1]:02x}" if ok else
                  f"HELLO {ip}: unexpected reply {len(data)}B")
        except OSError as e:
            print(f"HELLO {ip}: {e}")
        finally:
            s.close()


def main():
    resp = fetch_p2p()
    data = resp.get("data") or {}
    did = data.get("did")
    initstr = data.get("intstr")
    print("fields ok:", bool(did), bool(initstr))
    blob = open(SO, "rb").read()
    sbox = find_sbox(blob)
    hits, _ = brute_lut(initstr, blob)
    if not hits:
        print("STOP: LUT decode failed")
        return
    _, _, servers = hits[0]
    print("servers:", servers)

    hello_test(servers)

    import cs2pppp
    cs2pppp.configure_tables(prop_table=sbox)
    client = cs2pppp.Cs2Client(servers=servers, timeout=25.0)
    try:
        sess = client.session(did, timeout=25.0)
    except Exception as e:
        print("SESSION open failed:", type(e).__name__, str(e)[:300])
        # session object may not exist; retry manually to capture the log
        from cs2pppp.session import PpppSession
        s2 = PpppSession(real_did=did, servers=tuple(servers), port=DIR_PORT)
        try:
            s2.open(timeout=25.0)
        except Exception as e2:
            print("manual open failed:", type(e2).__name__, str(e2)[:200])
        for line in s2.log:
            print("  log:", line)
        return
    print("SESSION OPEN. via-log:")
    for line in sess.log:
        print("  log:", line)
    print("loopback:", sess.loopback, "peer:", sess.peer)
    if sess.loopback:
        sess.close()
        return
    # app-channel read-only probes
    try:
        ok = sess.ensure_app_channel(timeout=12.0)
        print("app channel GetDevInfo probe:", ok)
        for line in sess.log[-6:]:
            print("  log:", line)
    except Exception as e:
        print("app channel error:", type(e).__name__, str(e)[:200])
    for cmd in ({"cmd": "GetDevInfo"}, {"cmd": "GetDevExInfo"},
                {"cmd": "GetDevVideoInfo"}, {"cmd": "GetAlarmInfo"}):
        try:
            reps = sess.request_json(cmd, read_timeout=4.0)
            print(cmd["cmd"], "->", json.dumps(reps)[:400] if reps else "no reply")
        except Exception as e:
            print(cmd["cmd"], "error:", type(e).__name__, str(e)[:150])
    sess.close()
    print("session closed")


if __name__ == "__main__":
    main()

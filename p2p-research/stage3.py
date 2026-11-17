#!/usr/bin/env python3
"""Spectron PPPP dig, stage 3 (read-only): PPCS LAN search broadcast.

Sends LanSearch (0x30) and LanSearchExt (0x32) frames — plain and XOR1
(aiopppp dialect) — to the broadcast address on UDP 32108, and logs every
response with its source address. A PPCS device answers with a PunchPkt
(0x41) carrying its DID, which also reveals the camera's LAN IP.
"""
import socket
import struct
import sys
import time

sys.path.insert(0, "/Users/YOURNAME/pppp-dig/venv/lib/python3.9/site-packages")
sys.path.insert(0, "/Users/YOURNAME/pppp-dig/venv/lib/python3.13/site-packages")

from aiopppp.encrypt import xor1_encode  # noqa: E402


def frame(t, payload=b""):
    return struct.pack(">BBH", 0xF1, t, len(payload)) + payload


def main():
    targets = ["255.255.255.255", "192.168.1.X"]
    variants = {
        "plain-0x30": frame(0x30),
        "plain-0x32": frame(0x32),
        "xor1-0x30": xor1_encode(frame(0x30)),
        "xor1-0x32": xor1_encode(frame(0x32)),
    }
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("0.0.0.0", 0))
    s.settimeout(0.5)
    print("local sock:", s.getsockname())
    for name, pkt in variants.items():
        for tgt in targets:
            s.sendto(pkt, (tgt, 32108))
        print("sent", name)
    deadline = time.time() + 8
    seen = 0
    while time.time() < deadline:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        seen += 1
        head = data[:4].hex()
        print(f"RESP from {addr} len={len(data)} head={head} "
              f"body[:48]={data[4:52]!r}")
        # retry broadcasts midway in case the device was slow
        if seen == 1:
            for name, pkt in variants.items():
                for tgt in targets:
                    s.sendto(pkt, (tgt, 32108))
    print("total responses:", seen)
    s.close()


if __name__ == "__main__":
    main()

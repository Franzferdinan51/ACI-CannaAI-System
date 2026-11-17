#!/usr/bin/env python3
"""Stage 9: characterize the 443 service — close timing + protocol probes."""
import socket
import time

SRV = "18.221.228.168"


def probe(label, payload, wait=5):
    try:
        s = socket.create_connection((SRV, 443), timeout=8)
    except Exception as e:
        print(f"{label}: connect failed {e}")
        return
    s.settimeout(wait)
    t0 = time.time()
    try:
        if payload:
            s.sendall(payload)
        try:
            d = s.recv(4096)
            dt = time.time() - t0
            if d:
                print(f"{label}: {len(d)}B after {dt:.2f}s: {d[:48]!r}")
            else:
                print(f"{label}: FIN (clean close) after {dt:.2f}s")
        except socket.timeout:
            print(f"{label}: no data, still open after {wait}s")
        except ConnectionResetError:
            print(f"{label}: RST after {time.time() - t0:.2f}s")
    finally:
        s.close()


probe("idle (send nothing)", None)
probe("HTTP GET", b"GET / HTTP/1.0\r\nHost: x\r\n\r\n")
probe("garbage 32B", bytes(range(32)))
probe("envelope L=0", bytes([0, 0, 0x68, 0, 1, 2, 3, 4]))
probe("raw F1 6E DevLgn-ish", b"\xf1\x6e\x00\x44" + b"\0" * 68)

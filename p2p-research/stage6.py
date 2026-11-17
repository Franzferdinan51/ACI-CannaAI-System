#!/usr/bin/env python3
"""Stage 6: UDP first-contact variants phase 1 never tried + 2 TCP key shots.

- UDP HDR DevLgn (F1 6E 00 44 + CRCEnc(DevLgnWithDSK body)) to directory
  IPs on UDP 32108 / 32100 — plain SessionHeader framing, no envelope.
- UDP SDevLgn CRC (F1 92 00 18 + CRCEnc(UID20)) same ports.
- TCP TCPRlyReqDSK with layer-1 key = initstring / license.
Oracle: any reply bytes. Prints types/lengths only, never credentials.
"""
import json
import re
import socket
import struct
import sys
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq

CAM = "YOUR_CAMERA_DEV_ID"
BASE = "https://www.acinfinityserver.com"


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def udp_try(server, port, pkt, label, wait=6):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(wait)
    s.bind(("0.0.0.0", 0))
    lip, lport = s.getsockname()
    s.sendto(pkt, (server, port))
    try:
        data, addr = s.recvfrom(8192)
        t = data[1] if len(data) > 1 else None
        print(f"  {label} -> {server}:{port}: GOT {len(data)}B from {addr}, "
              f"head={data[:4].hex()} type=0x{t:02x}" if t is not None else
              f"  {label}: GOT {len(data)}B")
        if t == 0x6F:
            n = int.from_bytes(data[4 + 0x14:4 + 0x16], "big")
            names = data[4 + 0x28:4 + 0x28 + n].decode("ascii", "replace")
            print(f"      RELAY NAMES: {names}")
    except socket.timeout:
        print(f"  {label} -> {server}:{port}: silence ({wait}s)")
    except Exception as e:
        print(f"  {label} -> {server}:{port}: {type(e).__name__}: {e}")
    finally:
        s.close()
    return lip, lport


def main():
    data = fetch_p2p().get("data") or {}
    did = initstr = None
    for v in data.values():
        if isinstance(v, str) and re.fullmatch(r"[A-Z]{3,8}-\d{3,8}-[A-Z0-9]{3,8}", v):
            did = v
        if (isinstance(v, str) and len(v) >= 20
                and set(v.split(":", 1)[0]) <= set("ABCDEFGHIJKLMNOP")
                and len(v.split(":", 1)[0]) % 2 == 0):
            initstr = v
    dsk = data.get("key")
    crckey = data.get("crcKey")
    lic = data.get("lisence") or ""
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    srv = servers[0]
    print("target:", srv)

    # UDP HDR DevLgn — body needs a local sockaddr; use a placeholder LAN
    # addr first (server may not care for the name-list reply).
    body = gq.devlgn_body(did, dsk, "192.168.1.X", 32108, 0)
    hdr_udp = b"\xf1\x6e\x00\x44" + gq.crc_enc(body, crckey.encode())
    for port in (32108, 32100):
        udp_try(srv, port, hdr_udp, "UDP HDR DevLgn 0x6E")
    # UDP SDevLgn CRC
    sd = b"\xf1\x92\x00\x18" + gq.crc_enc(gq.pack_uid(did), crckey.encode())
    for port in (32108, 32100):
        udp_try(srv, port, sd, "UDP SDevLgn 0x92")
    # UDP plain DevLgn DSK (type 0x16 body format via UDP sender 0x6cd78?)
    pd = b"\xf1\x16\x00\x44" + gq.crc_enc(body, crckey.encode())
    udp_try(srv, 32108, pd, "UDP DevLgn 0x16")

    # TCP RlyReqDSK with remaining key candidates
    sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
    import stage5
    probe = socket.create_connection((srv, 443), timeout=8)
    lip, lport = probe.getsockname()
    probe.close()
    body = stage5.rlyreq_body(did, dsk, lip, lport, wi=False)
    inner = bytes([0xF1, 0x54]) + struct.pack(">H", len(body)) + body
    for klabel, k in (("initstr", initstr), ("license", lic)):
        stage5.attempt(srv, did, dsk, inner, klabel, k)


if __name__ == "__main__":
    main()

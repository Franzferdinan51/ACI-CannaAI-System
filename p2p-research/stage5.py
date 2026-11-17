#!/usr/bin/env python3
"""Stage 5: TCPRlyReq / TCPRlyReqDSKWI as first packet to directory:443.

RE finding: the client connect path (Connect_Do) never sends DevLgn — it
connects TCP to a directory server and sends RlyPreReq (TCPRlyReqDSK or
TCPRlyReqDSKWI) then TCPRlyReqDSK. Try both as first packet with the two
plausible envelope layer-1 keys. Oracle: any frame back / connection held.
Prints only labels, types, lengths — never credential values.
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


def rlyreq_body(did, dsk, local_ip, local_port, wi=False):
    b = bytearray(92 if wi else 76)
    b[0:20] = gq.pack_uid(did)
    b[0x14:0x14 + 8] = gq.pack_sockaddr(local_ip, local_port)
    b[0x2C] = 0  # flag = gNetInfo[3]
    b[0x2D:0x30] = bytes([5, 6, 1])
    b[0x30] = 0  # flag2
    b[0x34:0x34 + 24] = dsk.encode()[:23].ljust(24, b"\0")
    return bytes(b)


def attempt(server, did, dsk, inner, key_label, key_str, timeout=8):
    tag = f"type=0x{inner[1]:02x} key={key_label}"
    try:
        s = socket.create_connection((server, 443), timeout=timeout)
    except Exception as e:
        print(f"  {tag}: connect failed {e}")
        return
    s.settimeout(5)
    try:
        s.sendall(gq.wrap_tcp(inner, key_str))
        try:
            data = s.recv(8192)
            if not data:
                print(f"  {tag}: closed by peer (0 bytes)")
                return
            print(f"  {tag}: GOT {len(data)} bytes")
            if len(data) >= 8 and data[2] == 0x68:
                ln = int.from_bytes(data[0:2], "big")
                keyA = data[4:6]
                payload = data[8:8 + ln]
                ok = gq.tcprelay_checkcrc(payload) == data[6:8]
                pkt = gq.unwrap_tcp_payload(payload, keyA, key_str)
                print(f"      envelope len={ln} checkcrc_ok={ok} "
                      f"inner type=0x{pkt[1]:02x} inner len={len(pkt)}")
                if pkt[1] == 0x55 and len(pkt) >= 6:
                    print(f"      RlyReqAck: result={pkt[4]} sub={pkt[5]}")
            else:
                print(f"      raw head: {data[:16].hex()}")
        except socket.timeout:
            print(f"  {tag}: no reply in 5s (connection held)")
    except Exception as e:
        print(f"  {tag}: {type(e).__name__}: {e}")
    finally:
        s.close()


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
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    srv = servers[0]
    print("target:", srv)
    # local addr: use a throwaway connection to learn our source IP
    probe = socket.create_connection((srv, 443), timeout=8)
    lip, lport = probe.getsockname()
    probe.close()
    print("local addr:", lip, lport)
    for wi in (False, True):
        body = rlyreq_body(did, dsk, lip, lport, wi)
        inner = bytes([0xF1, 0x57 if wi else 0x54]) + struct.pack(">H", len(body)) + body
        for klabel, k in (("DID", did), ("empty", "")):
            attempt(srv, did, dsk, inner, klabel, k)


if __name__ == "__main__":
    main()

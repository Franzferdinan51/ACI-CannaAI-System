#!/usr/bin/env python3
"""Stage 4b: key-candidate sweep for the TCP envelope layer-1 key.

The directory closes instantly on our DevLgn — most likely the PropEnc
layer-1 key string (session +0x17c) is not the DID. Try a candidate set;
the oracle is: any bytes back / connection not instantly closed.
Prints only candidate labels and byte counts — never credential values.
"""
import json
import re
import socket
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


def try_one(server, did, dsk, crckey, key_label, key_str, inner_type=0x6E,
            netinfo3=0, envelope="full", timeout=6):
    try:
        s = socket.create_connection((server, 443), timeout=timeout)
    except Exception as e:
        return f"connect failed: {e}"
    s.settimeout(timeout)
    lip, lport = s.getsockname()
    body = gq.devlgn_body(did, dsk, lip, lport, netinfo3)
    inner = bytes([0xF1, inner_type, 0x00, 0x44]) + gq.crc_enc(body, crckey.encode())
    if envelope == "full":
        wire = gq.wrap_tcp(inner, key_str)
    else:  # PropEnc only, no TCPHead
        wire = gq.prop_enc(inner, key_str.encode() if key_str else b"")
    try:
        s.sendall(wire)
        s.settimeout(4)
        try:
            data = s.recv(4096)
            if data:
                out = f"GOT {len(data)} bytes back"
                # try full unwrap if it looks like an envelope frame
                if len(data) >= 8 and data[2] == 0x68:
                    ln = int.from_bytes(data[0:2], "big")
                    keyA = data[4:6]
                    payload = data[8:8 + ln]
                    inner_pkt = gq.unwrap_tcp_payload(payload, keyA, key_str)
                    out += f"; inner type=0x{inner_pkt[1]:02x} len={len(inner_pkt)}"
                return out
            return "closed by peer (0 bytes)"
        except socket.timeout:
            return "no reply within 4s (connection held open)"
    except Exception as e:
        return f"{type(e).__name__}: {e}"
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
    crckey = data.get("crcKey")
    lic = data.get("lisence") or data.get("license") or ""
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    srv = servers[0]
    print("sweep against", srv)
    candidates = [
        ("DID", did),
        ("empty", ""),
        ("DSK", dsk),
        ("crcKey", crckey),
        ("license", lic),
        ("DID-nodash", did.replace("-", "")),
    ]
    for label, k in candidates:
        r = try_one(srv, did, dsk, crckey, label, k)
        print(f"  key={label:12s} -> {r}")
    # envelope variant with the DID key
    r = try_one(srv, did, dsk, crckey, "DID", did, envelope="proponly")
    print(f"  key=DID proponly -> {r}")
    # plain inner type with DID key
    r = try_one(srv, did, dsk, crckey, "DID", did, inner_type=0x16)
    print(f"  key=DID type16   -> {r}")


if __name__ == "__main__":
    main()

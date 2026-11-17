#!/usr/bin/env python3
"""Spectron PPPP dig, stage 1 (read-only).

Fetches getP2PInfo in-process (credentials never leave this process / never
printed), locates the CS2 S-box in libgqipcsdk.so, brute-forces the 54-byte
InitString LUT from the same binary, decodes the init string to directory
servers, and runs a cs2pppp directory probe (Online/Offline) for the camera.
Prints only shapes for credential fields; server IPs are infrastructure.
"""
import json
import re
import sys
import urllib.request

CAM = "YOUR_CAMERA_DEV_ID"
BASE = "https://www.acinfinityserver.com"
SO = "/Users/YOURNAME/pppp-dig/libgqipcsdk.so"


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def shape(v):
    if not isinstance(v, str):
        return f"{type(v).__name__}={v!r}"[:80]
    cs = set(v)
    if v.isdigit():
        kind = "digits"
    elif cs <= set("ABCDEFGHIJKLMNOP"):
        kind = "A-P letters"
    elif cs <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"):
        kind = "alnum"
    elif cs <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:-_"):
        kind = "alnum+:-_"
    else:
        kind = "mixed"
    return f"str len={len(v)} charset={kind}"


def find_sbox(data):
    cnt = [0] * 256
    dup = 0
    for b in data[:256]:
        cnt[b] += 1
        if cnt[b] == 2:
            dup += 1
    if dup == 0:
        return data[:256]
    for i in range(1, len(data) - 256):
        ob, ib = data[i - 1], data[i + 255]
        if cnt[ob] == 2:
            dup -= 1
        cnt[ob] -= 1
        cnt[ib] += 1
        if cnt[ib] == 2:
            dup += 1
        if dup == 0:
            return data[i:i + 256]
    return None


def decode_with_lut(raw, lut):
    if ":" in raw:
        raw = raw.split(":", 1)[0]
    raw = raw.upper()
    if len(raw) % 2:
        return None
    out = bytearray()
    for i in range(len(raw) // 2):
        running = 0x39
        for j in range(i):
            running ^= out[j]
        raw_n = (ord(raw[2 * i + 1]) + (ord(raw[2 * i]) << 4) + 0xAF) & 0xFF
        out.append((lut[i % 0x36] ^ running ^ raw_n) & 0xFF)
    return bytes(out)


def plausible_servers(text):
    if not text or not text.endswith(","):
        return None
    if text.count(",") != 3:
        return None
    if not re.fullmatch(r"[0-9A-Za-z.\-,_]+", text):
        return None
    parts = [p for p in text.split(",") if p]
    if len(parts) != 3:
        return None
    for p in parts:
        if not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", p) and "." not in p:
            return None
    return parts


def brute_lut(raw, data):
    body = raw.split(":", 1)[0].upper()
    if len(body) < 8 or len(body) % 2:
        return None, None
    # first output byte must be a digit (IP start): filter lut[0]
    raw_n0 = (ord(body[1]) + (ord(body[0]) << 4) + 0xAF) & 0xFF
    want = {bytes([d ^ 0x39 ^ raw_n0]) for d in b"0123456789"}
    want = {w[0] for w in want}
    hits = []
    for off in range(0, len(data) - 54):
        if data[off] not in want:
            continue
        lut = data[off:off + 54]
        dec = decode_with_lut(body, lut)
        if dec is None:
            continue
        try:
            text = dec.decode("ascii")
        except UnicodeDecodeError:
            continue
        sv = plausible_servers(text)
        if sv:
            hits.append((off, lut, sv))
    return hits, None


def main():
    resp = fetch_p2p()
    print("getP2PInfo code:", resp.get("code"))
    data = resp.get("data") or {}
    for k in sorted(data):
        print(f"  field {k}: {shape(data[k])}")

    did = None
    initstr = None
    for k, v in data.items():
        if isinstance(v, str) and re.fullmatch(r"[A-Z]{3,8}-\d{3,8}-[A-Z0-9]{3,8}", v or ""):
            did = v
        if isinstance(v, str) and len(v) >= 20 and set(v.split(":", 1)[0]) <= set("ABCDEFGHIJKLMNOP") and len(v.split(":", 1)[0]) % 2 == 0:
            initstr = v
    print("DID field found:", bool(did), "| init-string field found:", bool(initstr))
    if not did or not initstr:
        print("STOP: missing DID or init string")
        return

    blob = open(SO, "rb").read()
    sbox = find_sbox(blob)
    print("S-box located:", bool(sbox))
    hits, _ = brute_lut(initstr, blob)
    print("LUT candidates:", len(hits or []))
    if not hits:
        print("STOP: no LUT candidate decoded to a plausible server list")
        return
    off, lut, servers = hits[0]
    print(f"LUT at .so offset {off:#x}; directory servers: {servers}")

    import cs2pppp
    cs2pppp.configure_tables(prop_table=sbox)
    client = cs2pppp.Cs2Client(servers=servers)
    try:
        res = client.probe(did, timeout=4.0)
        print("PROBE:", res.status, "code", res.code, "via", res.server)
    except Exception as e:
        print("PROBE failed:", type(e).__name__, str(e)[:200])


if __name__ == "__main__":
    main()

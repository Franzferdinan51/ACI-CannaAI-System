# Spectron 7 PPPP dig — notes (2026-11-16 evening)

Goal: open a direct P2P session to the author's Spectron 7 from the Mac Studio,
as groundwork for on-demand snapshots. Read-only probing only.
NO camera credentials (DID/license/key/init-string/crcKey) are stored here —
they are fetched in-process from the AC Infinity cloud at runtime.

## Verdict

The protocol family is confirmed, all crypto/identity material needed for a
classic session has been extracted and validated, BUT the classic UDP
directory path is dead silent — because this SDK fork's server path is the
newer **TCP-based HDR login (DevLgn with DSK) + TCP relay / RlyRdyPlus**
flow, not the classic UDP 32100 rendezvous. A live session was NOT achieved
this session; the remaining work is reconstructing the TCP DevLgn packet
format from the native library (or capturing the app's own login exchange).

## Confirmed facts

- App native libs (from `config.arm64_v8a.apk` in the AC Infinity app):
  `libgqipcsdk.so` and `libgqipcsdk_v1.so` both embed the CS2 PPCS SDK
  (internal C++ namespace `cs2p2p_*`: `cs2p2p_PPPP_Initialize`,
  `..._ConnectByServer`, `..._NetworkDetectByServer`, full PPCS_* error
  string table, APILicenseMatrix data). Java layer: `com.eternal.media.client.
  GqSdk` (`System.loadLibrary("gqipcsdk")`, `init(SY, APP_ID, intstr, false)`)
  and `GqClient` with ~60 JNI methods.
- App connect call: `nativeConnect(handle, did, keyStr, enableLanSearch,
  byServerString)` — i.e. this fork authenticates with the per-device **key
  (DSK)** from getP2PInfo, not just the DID.
- getP2PInfo fields (shapes only): did (17 chars), intstr (88 chars, A–P
  letters = classic PPCS InitString), key (16), lisence (6, their spelling),
  crcKey (8), rid, createTime, devId.
- **InitString LUT extracted** from libgqipcsdk.so at file offset 0x26cff
  (54 bytes; brute-forced against the real init string — unique candidate)
  and the init string decodes cleanly to 3 directory servers:
  18.221.228.168, 35.173.71.126, 54.183.197.109 (AWS us-east-2/us-east-1/
  us-west-1). Full tables in `tables.json` next to this file.
- **Session S-box extracted** at offset 0x26d75: the only 256-byte
  permutation window in either lib, identical in both, and byte-identical
  to aiopppp's published `XOR1_KEY_TABLE` — cross-validated. A 64-byte
  candidate CRC table sits contiguously between LUT and S-box (offset
  0x26d35); layout-inferred, not yet validated.
- Command vocabulary (JSON over the session DRW channel), from .so strings
  — 61 `JSON_CMD_*` names, incl. **JSON_CMD_SNAPSHOT_IMG** (on-demand
  snapshot), **JSON_CMD_AUTOPHOTO_SET** (periodic photos — the setting the
  cloud API refuses to write), JSON_CMD_SETTINGS_GET, JSON_CMD_SDCARD_GET,
  JSON_CMD_VPD_DATA_GET, JSON_CMD_VIDEO_START/STOP, JSON_CMD_TIMELAPSE_SET.
  JNI side mirrors these: nativeSnapshotImg, nativeSetTakePhotosRegularly,
  nativeGetIpcInfo, nativeLiveStart/Stop, etc.

## What was tried (all from the Mac, venv at ~/pppp-dig/)

- cs2pppp 0.2.11 directory probe (MSG_P2P_REQ, UDP 32100) to all 3 decoded
  servers: **timeout, zero replies**. Raw MSG_HELLO also silent. Port sweep
  (UDP HELLO to 32100/32108/32101/32102/32099/31100/8000/8600/9000/10000/
  12345/17520/20520/25100/30100/40100/50100/61100): silent. Full cs2pppp
  session open (relay + direct): fails at the directory stage (`relays=0`,
  `online=False`). Source-port binding to 32100/32108: no change.
  Mac UDP egress verified healthy (NTP + DNS replies fine).
- LAN search (aiopppp dialect): LanSearch 0x30 / LanSearchExt 0x32, plain
  and XOR1-encoded, broadcast to 255.255.255.255 and 192.168.1.X on UDP
  32108, 8 s listen: **zero responses**. (Camera still has no known LAN IP;
  its cloud "devMacAddr" is not an Ethernet MAC.)
- All 3 directory IPs **accept TCP 443** connections (no banner) — consistent
  with a login-first TCP service.
- Binary evidence for why UDP is silent: the immediate `32100` (0x7d64)
  appears **nowhere** in libgqipcsdk.so code, while `32108` (0x7d6c) is used
  10× (LAN search / TryLanTcp). The fork's server machinery is TCP:
  `cs2p2p_Do_TCPSendDevLgn`, `..._DevLgnDSK`, `..._TCPSendRlyReq`,
  `..._HDR_DevLgn` + `Proto_Read_HDR_RlyNameList`, `TCPRelay_Proprietary_
  Encrypt/Decrypt`, `TCPRelay_CheckCRC_*`, `RlyRdyPlus_*` punch protocol,
  `Proto_Send_SDevLgn` (UDP super-device login, possibly the directory
  first-contact in this fork).

## Most promising leads, ranked

1. **TCP HDR DevLgn on the directory IPs (port 443 is the live candidate)** —
   reconstruct `st_cs2p2p_DevLgn` / `Proto_Write_DevLgnWithDSK` /
   `Proto_TCPSend_HDR_DevLgn_DSK` from libgqipcsdk.so disassembly (Mac
   /tmp/dis.txt was a start; REA/Ghidra on the Mac would be faster), then
   implement DevLgn → HDR relay-list → TCPRlyReq in Python with the
   extracted S-box/CRC tables. All inputs (DID, key/DSK, license, crcKey)
   are already available from getP2PInfo.
2. **UDP SDevLgn** (`Proto_Send_SDevLgn`) — if the directory's first contact
   is a super-device-login packet rather than HELLO, reconstructing that one
   packet may unlock the classic flow cs2pppp already implements.
3. **LAN direct**: the fork has TryLanTcp + LanSearch with a bind-IP variant
   (`Send_LanSerchWithBindIP`). If the camera's LAN IP is ever identified
   (router DHCP table), a direct LAN session (LAN TCP) bypasses the
   directory entirely. The aiopppp-dialect broadcast got no answer, but the
   GQ LanSearch packet may carry a DID/body the aiopppp one lacks
   (`Send_LanSerch(const char*, int, int)` takes a string argument).

## Artifacts

- VM `~/workspace/spectron-pppp/`: this file, `tables.json` (LUT/S-box/CRC
  candidate + offsets), `stage1.py` (P2P-info fetch + LUT decode + probe),
  `stage2.py` (HELLO test + cs2pppp session attempt), `stage3.py` (LAN
  search broadcast).
- Mac `~/pppp-dig/`: venv (cs2pppp 0.2.11, aiopppp), the scripts, and
  `libgqipcsdk.so` (extracted from the app split APK).
- Mac `~/aci-re/out11|out12/`: jadx output for classes11/12 dexes —
  `com/eternal/media/client/GqClient.java`, `GqSdk.java`, v1 variants.

---

# Phase 2 (2026-11-16 evening – 2026-11-17) — rendezvous cracked, data phase blocked

Full protocol write-up lives in ~/workspace/ac-infinity-tools/SPECTRON-IPC.md
(P2P section). Key results:

- **Crypto fully verified**: PropEnc/RelayEnc/CheckCRC transliterations
  cross-checked against cs2pppp (100 iterations) and an independent
  re-derivation (300 inputs); my RlyReq packets are BYTE-IDENTICAL to the
  SDK's own output under Unicorn emulation of libgqipcsdk.so (emu1.py
  harness, Mac ~/pppp-dig/).
- **Key findings** (keyfinding.md): envelope layer-1 key = getP2PInfo
  `key` (DSK); CRCEnc runs with an EMPTY key on the client path (the
  `crcKey` field is never used by the app); session+0x194 (DSK field of
  the Proto writers) is empty in the app flow.
- **Handshake SOLVED live**: plain TCPRlyReq (inner 0x53, NOT the DSK
  variants) -> RlyReqAck result=0 x2 -> RlyRdy (device UID + 4-byte
  per-session token @body+0x14 + relay-node sockaddr @body+0x18; two
  alternating relay IPs, port 443). DevLgn is device-side only.
- **Data phase BLOCKED** (stage14-27): the directory connection FINs on
  any non-RlyReq packet; the relay node RSTs on any first packet; UDP is
  silent. All packet families golden-verified before sending (DC Req/Cmd,
  DRW, Alive, TCPRSLgn, JSON cmd 48). Leading theory: the camera's relay
  data binding is only live while the app holds a session — needs a
  co-test with the app's live view open. Secondary: TCPRSStart's
  struct-based sender is the one unresolved packet.
- **Command numbers**: SNAPSHOT_IMG=48, AUTOPHOTO_SET=47 (enable,
  interval) — from the .so's 62-entry command table + JSON template.
- **Timed photos WORK** via the author's in-app arming (P2P-side sync):
  unattended cloud shots at ~1 h spacing verified 2026-11-16 (19:20 main,
  19:52 under-canopy, visually confirmed).
- **MCP server shipped**: ~/workspace/ac-infinity-tools/mcp/ (aci_status,
  spectron_sensors, spectron_photos live-verified on the Mac;
  spectron_snapshot present as an experimental stub returning
  {available: false} until the data phase lands). Installed on the Mac at
  ~/ac-infinity-tools/mcp/ and registered in Hermes' config (Hermes not
  started). p2p_client.py is the drop-in slot for the snapshot client.

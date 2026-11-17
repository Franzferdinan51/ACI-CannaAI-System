# Spectron IPC — AC Infinity camera API dossier

Reverse-engineered 2026-11-16 by Juno (jadx decompile of the official Android
app v2.1.1 + live probing against the author' own account/camera). No public
documentation of this API exists anywhere as of this writing — every community
AC Infinity project covers controllers only. This file is the reference.

## The device

- Spectron 7 (AC-APM7), a UIS child of the 3x3 Tent Controller AI+.
- In `devInfoListAll` it appears as the tent device's `ipc` object:
  devType 10001, devId YOUR_CAMERA_DEV_ID, devCode YOUR_CAMERA_CODE,
  devMacAddr YOUR_CAMERA_MAC_ID, hardwareVersion 1.0.0, fw 1.3.5 at setup
  (the author updated the firmware 2026-11-16 evening).
- FCC: Spectron 3 (AC-APC7) and Spectron 7 are one electrically identical
  platform (AC Infinity's own model-confirmation letter, FCC 2AXMF-APC /
  2AXMF-APM; ODM Guangdong Seneasy; FCC test SW V1.3.2 / HW V1.1). Anything
  learned here applies to both.
- The camera announces NOTHING on the LAN: no mDNS/SSDP/ONVIF/RTSP (Home Link
  discovery + app decompile both confirm). Live view is P2P only.

## Cloud API contract (verified live)

Host: `https://www.acinfinityserver.com`
Auth: header `token` = the **`user_id`** value in `~/.config/aci/token.json`
(the file's keys are `user_id` and `email` — there is NO key named `token` or
`appId`; probes that read a guessed key sent an empty token and got 403s).
Shape for all IPC reads: **POST, parameters in the QUERY STRING, empty body.**
Do NOT send the `minversion` header to /api/ipc/* (it reroutes to a gateway
that 404s them).

| Endpoint | Params | Returns |
|---|---|---|
| POST /api/ipc/photoLogs | devId, startTime, endTime (epoch **seconds**), category 0–5 | photo records (see below) |
| POST /api/ipc/photoLogsDate | same | list of date strings that have logs ("2026-11-16") |
| POST /api/ipc/getSettingInfo | devId | full 51-field settings record |
| POST /api/ipc/getP2PInfo | devId | P2P DID + license + key + init string + crcKey — **credentials; never log or print them** |
| POST /api/ipc/getServerIp | devId | IPC socket gateway (serverDomain gwipc-us.acinfinityserver.com, socket port 6667) |
| GET /api/ipc/alerts | devId | alert list (empty so far) |
| POST /api/ipc/querySdCardInfo | devId | **500 even with correct auth** (unresolved, non-critical) |

### photoLogs semantics — the traps that cost hours

1. **Day-aligned windows ONLY.** The server answers one calendar day per
   query: startTime = local midnight, endTime = startTime + 86399 (this is
   exactly how the app's album queries — AlbumPopup.queryTimedPhotoLogs).
   A wide multi-day window silently returns `[]` even when photos exist.
   The date-index endpoint (photoLogsDate) contradicts an empty wide-window
   result — if the dates list is non-empty, photos exist; re-query per-day.
2. **Categories are overlapping filters, not partitions.** The same photo
   appears under several categories (0,2,3,5 returned identical records;
   category seems to be the app's "photo type" filter). Query all of 0–5
   and dedupe by `photoTime`.
3. Record fields: `photoTime` (epoch seconds), `downloadUrl` (signed S3 URL,
   bucket aci-ipc-prod, 7-day expiry — download promptly), `thumbsUrl`,
   `rid`, `temp`.
4. **Manual captures from the app DO upload** (verified 2026-11-16: three
   shots from one app session — main-cam 4K + under-canopy — all pulled).
   Both cameras (main + UVC under-canopy) land in the same log.
5. Photos carry a burned-in "AC INFINITY" watermark + timestamp (main cam).

Tool: `aci-photos` (Mac ~/bin/aci-photos; master in this directory) —
iterates day windows, dedupes, lists and `--download DIR`.

### Sensor data (no IPC call needed)

The camera's sensors ride inside the `ipc` object of `aci raw`
(devInfoListAll), ×100 ints: thermalImagingSensorOnline, thermalCenter
(= leaf temp, °C×100; mirrored in insideTemp/insideTempF), thermalAvg/Min/Max,
climateSensorOnline, temperatureF, humidity, vpdnums (leaf-aware VPD).
First read 2026-11-16: leaf 63.0°F vs 71.7°F air; cam VPD 0.70 vs probe 0.82.

### Settings — read works, write does NOT (yet)

- getSettingInfo fields of note at setup: autoPhotoStatus 0,
  autoPhotoInterval null, timeInterval null, timeLapseStatus 0,
  uvcAutoPhotoStatus null, uvcAutoPhotoInterval 60, uvcAutoPhotoUpload 1,
  videoResolution 5, timeZone "GMT+5" (stored value — do not "fix").
  Backup of the original record: Mac ~/cannaqwen-v3/ipc-settings-orig.json.
- Write endpoint: POST /api/ipc/setting, form-encoded map
  {fields…, devId, cmd}. cmd codes (from IpcSettingRepository):
  51 timelapse, 59 auto-photo status, 516 side-cam auto-photo, 58 timezone,
  510 resolution, 512 plant AI, 514 temperature display, 515 sensor readings.
- **WRITE MATRIX — RESOLVED 2026-11-16 late (phone-free trigger dig).**
  Exact app construction (IpcSettingRepository): form map = ONLY the
  setting field(s), then devId, then cmd appended last; POST
  /api/ipc/setting @FormUrlEncoded. cmd 512 routes to the service's
  updateCamareAI method (15 s timeouts); all other cmds → updateSettingInfo
  (60 s). Full cmd table: 51 timelapse, 52 videoMode, 53 mirrorMode,
  54 watermark, 55 displayDataRate, 56 fillLight, 57 indicatorLight,
  58 timeZone, 59 autoPhotoStatus, 510 videoResolution, 511 eject SD,
  512 plant-AI {plantAi, aiVisionOverlay, tentDoorOpen}, 514 unit,
  515 sensorReadings, 516 uvcAutoPhotoStatus, 517 sideCamera.
  Live no-op probes (values = current getSettingInfo values), classic
  token header: **cmd 515 → code 200 "success"** (the ONLY success — a
  server-owned display preference); **cmds 54, 59, 516 → code 500**
  (server attempts and fails downstream); **cmds 52, 53, 55, 56, 57, 58,
  510, 514 → code 999999** (validation rejection). Extra form field
  (appId) poisons any write → 999999. Params in query string + empty
  body → 500. Mode-A headers (minversion:"", devType:"") change nothing.
  Trigger test: cmd 59 {autoPhotoStatus=1} and cmd 516
  {uvcAutoPhotoStatus=1} writes + photoLogs polling ×3 each — **no
  off-cadence photo**; full-day audit confirms every 2026-11-16 photo
  after 19:20 sits exactly on the :20/:52 timed cadence. Root cause:
  the cloud write path is auxiliary/legacy — in app v2.1.1 the settings
  UI executes via IpcSettingViewModel → P2P CmdSync callbacks, and
  IpcSettingRepository is injected ONLY into the plant-AI Knowledge
  ViewModels. Camera-executed settings are P2P-only by design.
- The signed refresh-token mode (RefreshTokenInterceptor Mode B) is
  **unreachable in practice**: um7.fetchNewTokenIfNeeded has NO callers
  in the decompile; POST /api/auth/newToken → 404 (Spring "No message
  available"), POST /auth/newToken → nginx 405. Not the missing piece.
- The app syncs settings to the camera over its P2P channel
  (GqClient.setTakePhotosRegularly(0, interval, …) fires when auto-photo
  is enabled) — a cloud write alone was never going to arm the camera.
- State 2026-11-16 evening (updated): the author enabled timed photos in the
  app; cloud settings still read autoPhotoStatus 0, BUT unattended photos
  DID land (~1 h spacing, verified visually) — the app arms the camera
  over its P2P channel and the cloud record simply doesn't reflect it.
  Timer arming is proven only by a photo arriving while nobody is in the
  app — which is now the observed state.

## P2P (dig phases 1–2 done 2026-11-16/17 — rendezvous CRACKED, data phase open)

- **Confirmed: CS2 PPCS.** Both app native libs (libgqipcsdk.so,
  libgqipcsdk_v1.so) embed the CS2 SDK (internal cs2p2p_* symbols, full
  PPCS_* error table). Java layer: GqSdk.init(SY, APP_ID, intstr) +
  GqClient.nativeConnect(did, keyStr, enableLanSearch, byServerString) —
  this fork authenticates connects with the per-device **key (DSK)** from
  getP2PInfo. TUTK ruled out.
- Extracted + validated (in ~/workspace/spectron-pppp/tables.json): the
  54-byte InitString LUT (brute-forced from the .so; the account init string
  decodes to 3 AWS directory servers us-east-2/us-east-1/us-west-1) and the
  256-byte session S-box (byte-identical to aiopppp's published XOR1 table).
- The classic UDP path is vestigial in this fork — directory servers answer
  NOTHING on UDP. All 3 directory IPs serve **TCP 443**.

### Wire format (all byte-verified against the SDK via Unicorn emulation)

- **TCP envelope** (every TCP packet): head = `{len u16BE, 0x68, 0x00,
  keyA[2] random, CheckCRC[2]}` + payload, where payload =
  RelayEnc(PropEnc(inner)). PropEnc = the session S-box cipher (tables.json
  @0x26d75) keyed by a string; layer 1 key = the **DSK** (getP2PInfo `key`,
  copied into the session at Connect_Do from the after-`:` part of the
  `intstr + ":" + key` string Java passes). RelayEnc = PropEnc keyed by
  `"%02X%02X" % keyA`. CheckCRC = dual-ended rolling XOR seeded "CS"
  (verified against the raw listing over 300 random inputs).
- A **NoEncrypt envelope** variant exists (head keyA/CRC zeroed, payload =
  PropEnc only) — used by a parallel send family; the live servers reject
  it for the data phase too (tested).
- **CRCEnc** (DevLgn bodies): the client path runs it with an **EMPTY**
  key (the (1,3,5,7) stride schedule) — `cs2p2p_gCRCKey` is only installed
  device-side by the license check. getP2PInfo's `crcKey` field is never
  passed to the SDK by the app.

### The rendezvous handshake — SOLVED and reproduced live

The client uses the **plain (non-DSK) RlyReq**, not the DSK variants and
not DevLgn (DevLgn is the *device-side* login; the directory kills it from
a client). On one TCP connection to any directory server:

1. **TCPRlyPreReq** then **TCPRlyReq** — inner type **0x53**, 52-byte body:
   header `F1 53 00 34`; UID (prefix strncpy 7 @+0, serial u32BE @+8,
   check strncpy 7 @+12); my sockaddr (wire form: family u16BE, port
   u16LE, IPv4 octets reversed) @+0x14; flag byte (gNetInfo[3], 0 works)
   @+0x1C; bytes {05 06 01} @+0x2D; flag2 @+0x30 (PreReq=0, RlyReq=1).
   My reconstruction is **byte-identical** to the SDK's own
   Proto_TCPSend_TCPRlyReq output (golden emulation).
2. Server replies **RlyReqAck** (type 0x55, result=0) twice (sub=0, sub=1),
   then **RlyRdy** (type 0x52, 52 B). RlyRdy body: device UID (20 B), a
   **4-byte per-session token @+0x14**, and a sockaddr @+0x18 naming a
   **relay node** (two alternating AWS IPs seen, port 443).
3. The directory connection is a **pure rendezvous service**: it answers
   repeated RlyReq pairs indefinitely, stays open ≥24 s in silence — and
   **instantly closes (clean FIN) on ANY other packet type**.

### The data phase — precise blocker (phase 2, 2026-11-17)

Everything after RlyRdy was reconstructed from the SDK and golden-verified
(DC Req 76 B type 0xDC/D1 01; DC Cmd type 0xDC/D1 11 with 76-byte header;
DRW type 0xD0; Alive F1 E0; TCPRSLgn type 0x50 with token + relay-IP quad
+ sockaddr; JSON envelope `{"version":"1.0","ack":false,"seq":%u,
"cmd":%d,"def":"…"}`; **command numbers: AUTOPHOTO_SET=47 (two int args:
enable, interval), SNAPSHOT_IMG=48 (no args)**) — and every live variant
was refused:

- Directory connection, post-RlyRdy: DC Req, DC Cmd, DRW (bare JSON /
  DC-wrapped / bare DC), Alive, TCPRSLgn, DevLgn — in full **and**
  NoEncrypt envelopes, on one server, on all 3 simultaneously → FIN.
- Relay node (from RlyRdy): bare TCP connect holds silently, but any
  first packet (TCPRSLgn in 5 envelope/key variants, RlyReq) → **RST**.
- UDP datagrams (6 forms) to relay + directory :443 → silence.

Two untested explanations remain, in order of likelihood:
1. **The camera's relay data binding is only live while/recently after
   the app holds a session.** Every probe ran hours after the last app
   use; RlyRdy may be served from a stale registration. Test: probe
   while the author holds the app's live view open.
2. An extra client→relay binding packet sent via function-pointer
   dispatch not yet identified (the one unresolved sender is
   TCPRSStart, whose argument layout is struct-based).

The SDK's documented data path is PPCS_Write → thread_send_DRW with the
session key (= DSK) — so when the binding is live, DRW/DC as built here
is the expected shape. Full evidence trail: stage4–stage27 scripts +
emu*.py harnesses in ~/workspace/spectron-pppp/ and Mac ~/pppp-dig/.

### Command surface

61 JSON_CMD_* names; the JSON command template and the 62-entry command
table (in the .so) give: SNAPSHOT_IMG = cmd **48**, AUTOPHOTO_SET = cmd
**47** (args: enable, interval), plus SETTINGS_GET, SDCARD_GET,
VPD_DATA_GET, VIDEO_START, TIMELAPSE_SET, etc.

### Timed photos — WORKING (via the app's own P2P sync)

the author enabled timed photos in the app; the app syncs the setting to the
camera over its P2P channel (the cloud record still reads
autoPhotoStatus 0 — it does not reflect P2P-side arming). Verified
2026-11-16: unattended shots landed in the cloud log at ~1 h spacing
(19:20 ET main cam, 19:52 ET under-canopy; the 19:52 frame was downloaded
and visually verified — the current crop seedlings in the tent). Pull them with
`aci-photos` like any other cloud photo.

## Decompile workspace

Mac ~/aci-re/: jadx 1.5.6 (~/aci-re/jadx/), dexes (~/aci-re/dex/), outputs
out5–out10. Key sources:
- out7 …/common/data/api/IpcApiService.java — the retrofit IPC interface
- out7 …/common/data/repository/IpcRepository.java — call wrappers
- out9 …/ipc/data/repository/IpcSettingRepository.java — setting writes + cmd codes
- out9 …/ipc/popup/AlbumPopup.java — album query shape (day windows)
- out9 …/ipc/domain/vm/IpcSettingViewModel.java — P2P sync side-effects
- out6 …/acinfinity/HeaderInterceptor.java — app header set
- out5 defpackage/ou5.java — RefreshTokenInterceptor (minversion/devType)
APK banked at ~/workspace/aci-apk/com.eternal.acinfinity.apk.

## Research (2026-11-16, sourced)

Full report: ~/workspace/research_notes/spectron-camera-api-research-20261116-2354/report.md
Headlines: zero public IPC documentation; controllers-only community projects
(dalinicus HA, ober37 MCP — API.md has no camera endpoints); Spectron 3 = 7
hardware per FCC; PPPP/CS2 attribution from DID + license fingerprints;
one reviewer runs Spectron 7 timed photos at 6 h intervals; no public reports
of toggles not sticking or firmware resetting camera settings.

## Phone-free trigger dig — 2026-11-16 late (routes 1–4, ALL NEGATIVE)

Requirement: an on-demand trigger with no phone dependency (Mac/Robin/
Home Link hosting all approved). Verdict: **NOT FOUND.** Detail per route;
full log in the goal progress.md.

- **Route 1 — live-start cloud trace: no missing call exists.** The full
  IpcApiService surface was enumerated. Live-view startup's cloud calls
  are ONLY: GET /api/ipc/intstr (SDK-init, account-level; verified live
  200 — same init-string data getP2PInfo already provides), getP2PInfo,
  getServerIp, getSettingInfo. No session-authorization / live-token /
  open-stream endpoint exists anywhere in the app. IpcDeviceSession
  makes zero cloud calls. A missing REST call does NOT explain the
  standalone-P2P data-phase refusal.
- **TAKE PHOTO button — traced end-to-end (the author' ask).** Chain:
  IPCPlayerCover.rtvTakePhoto → clickWithTrigger (synthetic vx2) →
  IPCPlayerCover.initView$lambda$10 → player view resetToDefault() →
  SmartCameraViewModel.onTakePhotoClicked(View) →
  requestPermissionAndCreateFile(ctx, "Image/Snapshot", …) →
  C01001: ViewHardwareRecorder.captureSingleFrame(videoView, path) →
  onTakePhotoClicked$1$1$1: PhotoAnimation effect + toast "photo saved
  to your phone's gallery". **It is (c): a purely local grab of the
  currently rendered stream frame, saved phone-locally. No cloud REST
  call, no P2P command.** The camera's true still capture is a SEPARATE
  path (HD photo mode): PhotoRequestCoordinator (MANUAL lane) →
  HDPhotoManager.capturePhoto/captureMainPhoto/captureSubPhoto →
  GqClient.snapshotImg/subSnapshotImg → JNI nativeSnapshotImg →
  JSON_CMD_SNAPSHOT_IMG (48) over the P2P session; frame returns over
  P2P. Also zero cloud REST. **There is NO photo upload endpoint in the
  app** — the only /api/ipc/upload* route is upload/deletePhotos
  (delete). App-triggered captures appear in cloud photoLogs because
  the CAMERA uploads its own captures device→cloud.
- **Route 2 — setting writes:** see the resolved write matrix in the
  Settings section above. No cloud write arms or fires a capture.
- **Route 3 — controller surface: nothing.** Live `aci raw`: no
  `ipcSetting` key anywhere in the account device data (ober37's
  "always-null" = absent here); no photo/snap keys at all. The tent
  controller's record embeds the camera's descriptive device-info
  object (flags: cameraSeries, ipcPro, mqttIPC, pauseCamera state) —
  no settings or trigger surface. All decompiled camera actions
  (pauseCamera, lockUnlockIpc, rebootIpc, modIpcName, formattedSdCard)
  are camera-devId-addressed via /api/ipc/*. Home Link in-home
  discovery corroborates: no local advertisement from camera or
  controller (cloud-only by design); Home Link cannot do BLE control
  or UDP/multicast control traffic in any case.
- **Route 4 — BLE: not plausible as a trigger.** hunterjm's
  ac-infinity-ble (v1.0.0) + HACS integration speak BLE to the
  CONTROLLER: per-port climate loads (fan/light/number/output/switch
  entities), telemetry, modes. No camera entity or capture function
  exists in that stack; the README explicitly excludes "secondary
  device functions". The camera is not a BLE peripheral — it is a
  Wi-Fi/UIS device driven via cloud/P2P. Reaching it via BLE would
  require undocumented protocol RE in the APK's base.protocol with no
  supporting evidence, a BLE host within ~30 ft of the tent (the Mac
  is not), and winning the controller's single-BLE-client slot from
  the phone app. Scoped and closed.
- **USB lead: CLOSED by the author** — the camera's USB plug is power
  only; no plug-in test will happen.
- **What remains:** the timed-photo cadence (:20 main / :52 side ET)
  is the only phone-free capture mechanism that exists in this
  system's design; the ADB/app route stays a fallback only. Any
  future on-demand path would have to come from the native-P2P data
  phase opening (blocked vendor-side, protocol space exhausted) or a
  future app/firmware change adding a cloud capture endpoint.

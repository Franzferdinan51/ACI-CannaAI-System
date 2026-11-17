---
name: local-ac-infinity
description: Read and control the author's AC Infinity controllers (3x3 Tent + Clone Chamber) through their cloud API with the `aci` CLI on the Mac Studio — live temp/RH/VPD readings and per-port levels/modes, replacing the old ADB screencap scrape. Use when the author asks about tent/clone-chamber conditions, grow gear state, or wants a fan/light/humidifier changed or the tent paused/unpaused.
---

# AC Infinity — cloud API tool (`aci`)

The controllers have no local API (LAN-silent, outbound-only — confirmed by
port probe 2026-11-03). Control goes through AC Infinity's cloud, the same
unofficial API the phone app uses, implemented from the community reference
client (dalinicus/homeassistant-acinfinity). Built 2026-11-03.

## Setup state

- Tool: `~/ac-infinity-tools/aci.py` on the Mac (master: `~/workspace/ac-infinity-tools/`), wrapper `~/bin/aci`. Stdlib-only; runs on /usr/bin/python3.
- Auth: DONE 2026-11-03 (his password was right first try). `~/bin/aci-login` — ONE interactive run in a Mac Terminal. Prompts for the AC Infinity email/password, stores ONLY the account token at `~/.config/aci/token.json` (600). Password never stored. If the token ever dies, re-run it. His account email is his Gmail (you@example.com); the password is AC Infinity's own, not the Gmail password.
- **Cloud sync lag on writes is real**: a mode write can read back stale for ~1 min (the `set` command polls up to ~90s before believing the result). Don't judge a write by an instant re-read.
- **The AI program is the real pause layer — RESOLVED 2026-11-03** by decompiling the official app (v2.1.1, jadx): AI controllers run an "ML" program (GET `/api/dev/ml/byDevId/{devId}`) whose `state` field is the switch — **0 = paused, 1 = AI running, 2 = TentWork session** (a timed work burst; when its countdown ends the program settles into state 1, it does NOT go back to paused). While the program runs (state 1/2) it overrides port modes entirely — port OFF/AUTO writes read back fine but change nothing physical. The app flips state by POSTing the whole record to `POST /api/dev/ml` as a form field map containing ONLY the NetMlInfo wire fields (lists ride as the `portDetailsStr`/`portSensorsStr` JSON companions); echoing the GET record verbatim is rejected with code 999999. `aci pause`/`aci on` implement exactly this and verify state + watched settings after the write. Ground truth is still physical: port levels in `aci status` (the `speak` field) or the author's eyes — never a mode read-back. History: setting ports OFF→AUTO on 2026-11-03 did nothing because the program was dormant at state 0; the morning's "paused" tent was that dormant state.
- His tent controller is devType 20 (Controller AI+) → the modeAndSetting PUT path; the Clone Chamber is devType 11 → addDevMode path.
- Status readings: `deviceInfo` headline = the controller's own sensor (outside); the `sensors` array carries the probe (accessPort 1 = inside). A controller with no probe (Clone Chamber) reports sentinel garbage — the tool prints "sensors not reporting" instead.
- API quirks: host `https://www.acinfinityserver.com`; login field is literally `appPasswordl`; the API truncates passwords to 25 chars (the app does the same); auth = the login response's `appId` sent as the `token` header.

## Commands (run via ~/bin/mac-ssh)

- `aci status` — every controller: inside readings (°F, %RH, VPD) + each port's name, current level, on/off. Readings in `deviceInfo` are ×100 ints (`temperatureF`, `humidity`, `vpdnums`).
- `aci controllers` — names, devIds, codes, types, firmware.
- `aci port <match> <n>` — full mode settings for one port (mode/atType, speeds, triggers) and prints any unfamiliar keys — use this to hunt unknown states (e.g. what "paused" maps to) before changing anything.
- `aci set <match> <n> --level N|--on|--off|--auto` — control write. Faithful port of the reference client: re-sends the port's full current settings with only the requested fields changed (standard path `addDevMode`; AI-controller devTypes 20/21/22 use the `modeAndSetting` PUT with modeAndSettingIdStr per mode). **Every set verifies by re-reading the port afterwards** — trust that read-back, not the write. Note: on an AI controller whose program is running, port writes are overridden by the program (see the pause layer above).
- `aci ml <match>` — the AI program: state (paused / AI running / TentWork + countdown), targets, AI-selected ports, night targets.
- `aci pause <match>` — the real pause: AI program state → 0 (verified, settings watched) + all ports OFF, then a status read-back.
- `aci on <match>` — AI program state → 1 (the app's On button); the AI drives its selected ports to target.
- `aci tentwork <match>` — PUT `/api/dev/ml/tentWork`: start a TentWork session (timed burst, default 15 min). The AI stays ON afterwards — follow with `aci pause` to stop it for real.
- `aci raw` — full devInfoListAll JSON for debugging.

`<match>` = substring of controller name/code, e.g. `aci port tent 1`.

## His gear

- **3x3 Tent** (code H-TENTCODE): port 1 Grow Light, 2 Fan, 3 Exhaust Fan, 4 Humidifier (5/7/8 unused, 6 unconfigured as of Oct 2026).
- **Clone Chamber** (code G-CHAMBERCODE): Grow Light + Growlight + spares; its sensors have historically read dashes (no probe data).
- 2026-11-03 end state: tent AI woken via TentWork (verified physically running + WeedCam photo), then **paused again at the author's order** (no plants in the tent right now) — state 0, all ports level 0, program targets intact (70–80°F, 30–50% RH, VPD 0.80–1.20, ports 1,2,3,4,6).

## Spectron 7 camera (set up by the author 2026-11-16)

- The camera is a UIS child of the 3x3 Tent controller — in `aci raw` it is the
  tent device's `ipc` object (devType 10001, devId …710774, code YOUR_CAMERA_CODE,
  fw 1.3.5). It does NOT appear in `aci controllers`/`aci status` output.
- **Sensor data IS readable now** from `deviceInfo` inside `ipc` (×100 ints):
  `thermalImagingSensorOnline` (1 = live), `thermalCenter`/`thermalAvg`/
  `thermalMin`/`thermalMax` (°C×100 — thermalCenter = leaf temp; also mirrored
  in `insideTemp`/`insideTempF`), `climateSensorOnline`, `temperatureF`,
  `humidity`, and the camera's own `vpdnums` (leaf-aware VPD). First read
  2026-11-16: leaf center 63.0°F vs 71.7°F air, cam VPD 0.70 vs probe 0.82.
- **Photos: READ PATH CRACKED 2026-11-16 (jadx decompile of the banked APK).**
  Local interception is impossible: the camera announces nothing on the LAN
  (Home Link discovery: no mDNS/SSDP; the app has no RTSP/ONVIF code) — live
  view is cloud P2P via `/api/ipc/getP2PInfo` (returns did/license/key —
  credentials, never log them). The working cloud contract for ALL ipc reads:
  **POST with params in the QUERY STRING, empty body, header `token` = the
  `user_id` value from ~/.config/aci/token.json** (NOT a key named appId/token
  — probes that read the wrong key sent an empty token and got 403s).
  Endpoints verified 200: photoLogs + photoLogsDate (params devId, startTime,
  endTime in epoch SECONDS, category 0–5), getP2PInfo, getSettingInfo,
  getServerIp, alerts. **photoLogs only answers DAY-ALIGNED windows** (one
  calendar day per query: startTime = local midnight, endTime = +86399 —
  the app's album query shape); a wide multi-day window silently returns
  []. Categories are overlapping filters, not partitions — dedupe by
  `photoTime`. Records carry `downloadUrl` (signed S3, 7-day expiry),
  `thumbsUrl`, `photoTime`. **Manual captures from the app DO upload** —
  first pulls 2026-11-16 18:49–18:52 ET: main-cam 4K shot + under-canopy
  shot, both verified visually. Tool: **`aci-photos`** (~/bin/aci-photos on
  the Mac; master in ~/workspace/ac-infinity-tools/) — day-window queries,
  lists and downloads. Cloud settings still read autoPhotoStatus 0 /
  timeLapseStatus 0 / uvcAutoPhotoStatus unset (uvc interval 60, upload 1)
  even after the author enabled timed photos in the app 2026-11-16 evening —
  whether the timer is truly armed is proven only by an unattended shot
  landing.
- **Enabling photo modes from the API is NOT cracked:** /api/ipc/setting is a
  form POST of {fields…, devId, cmd} — cmd codes from IpcSettingRepository:
  51 timelapse, 59 auto-photo status, 516 side-cam auto-photo, 58 timezone,
  510 resolution, 512 plant AI. App-shaped writes (incl. the app's
  HeaderInterceptor headers: token, appVersion 2.1.1, phoneType 2,
  languageType, minversion/devType from the RefreshTokenInterceptor) still
  return 500 — the app also syncs settings to the device over its P2P channel
  (gqClient.setTakePhotosRegularly), and a refresh-token auth subsystem
  (/api/auth/newToken) exists in the app. Practical route: the author enables
  Auto Photo in the app once; `aci-photos` pulls from then on.
- **Timed photos: WORKING (verified 2026-11-16 evening).** the author enabled
  Auto Photo in the app; unattended shots landed in the cloud log at ~1 h
  spacing (19:20 ET main cam, 19:52 ET under-canopy — the latter visually
  verified: the seedlings in frame). The cloud settings record STILL reads
  autoPhotoStatus 0 — it does not reflect the app's P2P-side arming; judge
  arming by photos landing, never by the settings record.
- **P2P phase 2 (2026-11-17): rendezvous handshake CRACKED, data phase
  blocked.** The TCP envelope + plain TCPRlyReq handshake against the 3
  directory servers is byte-verified (my packets are identical to the
  SDK's own) and reproduces live: RlyReqAck result=0 → RlyRdy carrying a
  per-session token + relay node. But every reconstructed data packet
  (DC/DRW/Alive/TCPRSLgn, both envelope forms) is refused — directory
  FINs, relay node RSTs. Leading theory: the camera's relay data binding
  is only live while the app holds a session; needs a co-test with the
  app's live view open. Command numbers learned: SNAPSHOT_IMG=48,
  AUTOPHOTO_SET=47. Full protocol section: SPECTRON-IPC.md.
- **MCP server (2026-11-17):** ~/workspace/ac-infinity-tools/mcp/ (Mac:
  ~/ac-infinity-tools/mcp/, registered in Hermes' config) — stdio tools
  `aci_status`, `spectron_sensors`, `spectron_photos` (live-verified) and
  `spectron_snapshot` (experimental stub — returns available:false until
  the P2P data phase lands; p2p_client.py is the drop-in slot).
- Community references (ober37 API.md, both HA forks) document ZERO camera
  endpoints — this subsystem is undocumented publicly. Decompile workspace:
  Mac ~/aci-re/ (jadx 1.5.6 + out5–out10 sources).
- **Full dossier: ~/workspace/ac-infinity-tools/SPECTRON-IPC.md** (endpoint
  table, traps, cmd codes, P2P state, file map). Read it before deep IPC work.
- **Photo playbook (grow checks):** run `aci-photos --days 2 --download
  ~/spectron-photos` on the Mac, pull the newest main-cam frame with
  mac-scp-pull, and read it alongside the Pixel/Blink shots — the Spectron
  overhead view is the best of the three (labels readable, all four plants
  in frame). The under-canopy frame (smaller file, no watermark) covers
  soil level. Also pull leaf temp + leaf VPD from the `ipc` object in
  `aci raw` on every check. If `aci-photos` returns nothing, first check
  photoLogsDate for a date entry before concluding there are no photos —
  and never query photoLogs with a multi-day window (silently empty).

## Safety

- Reads are free — run them anytime.
- **Control writes change real grow equipment.** Only fire `aci set` when the author ordered that exact change (e.g. "unpause my tent", "set the exhaust to 8"). No speculative tweaks, no "optimizing" his climate. A wrong light/fan change costs plants, not tokens.
- If a write's read-back doesn't show the change, report it — don't retry blindly.

## Dashboard feed (updated 2026-11-03 night)

The dashboard bridge's environment feed (~/dashboard-bridge/acinfinity.json, passed through verbatim at bridge :8901 /api/cannaai) is now written by **~/bin/acinfinity-apifeed.py** (master: ~/workspace/ac-infinity-tools/) — same JSON shape as the scrape produced ({fetched_at, devices[{name, id, inside, outside, ports}], alerts: []}), but sourced from this API tool: inside = accessPort-1 probe (sensorTypes 0/2/3), outside = deviceInfo headline readings (sentinel-guarded), ports carry real mode labels via get_mode_settings + AT_TYPES, ids keep the app-style prefixes (H-TENTCODE / G-CHAMBERCODE). The existing LaunchAgent `com.example.acinfinity-collect` (600 s) now runs the API feed (plist backup: .plist.scrape-era.bak; last scrape-era JSON: acinfinity.json.scrape-era.bak). **The Moto G scrape was retired as the feed source at the author's order** — its every-10-min foregrounding of the AC Infinity app was wigging out the Muse app on that phone.

The older ADB route still exists as a manual fallback only: `~/bin/acinfinity-collect.sh` scrapes the app on the Moto G (serial YOUR_PHONE_SERIAL, package com.eternal.acinfinity) when the phone is awake/unlocked — read-only, ADB drops often. Do not re-enable it as a scheduled feed without the author's word.

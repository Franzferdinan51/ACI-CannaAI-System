---
name: ac-infinity
description: Read the author' AC Infinity controllers (3x3 Tent + Clone Chamber) and Spectron 7 camera through the cloud API tools on this Mac — live temp/RH/VPD, port state, camera leaf temp/VPD, and pulling Spectron photos. Use when the author asks about tent conditions, grow gear state, or wants Spectron camera photos.
---

# AC Infinity — cloud API tools (Hermes copy)

You are on the author' Mac Studio. The tools run LOCALLY in your terminal —
no SSH wrapper. Juno (the primary agent) maintains the master copies; this
skill is your working copy so you can do the same reads if Juno is cut off.

## Tools

- `~/bin/aci status` — every controller: inside readings (°F, %RH, VPD) +
  each port's name/level/on-off. Readings are ×100 ints.
- `~/bin/aci controllers` — names, devIds, codes, types, firmware.
- `~/bin/aci raw` — full device JSON (the Spectron camera lives in the tent
  device's `ipc` object — see below).
- `~/bin/aci-photos [--days N] [--download DIR]` — list/download Spectron 7
  photos from the cloud (see photo rules below).
- Auth: token at ~/.config/aci/token.json (keys: `user_id`, `email`). If API
  calls return 403, the token died — tell the author; re-login is
  `~/bin/aci-login` (interactive, his password — never ask him to paste it
  to you in chat; he runs it in Terminal).

## Safety

- Reads are free — run them anytime.
- **Control writes change real grow equipment** (`aci set`, `aci pause`,
  `aci on`): only on the author' explicit order for that exact change. A wrong
  light/fan change costs plants. If a write's read-back doesn't show the
  change, report it — don't retry blindly.
- The tent runs an AI program that overrides port modes while active;
  `aci ml tent` shows its state (0 paused / 1 running / 2 TentWork).

## Spectron 7 camera (set up 2026-11-16)

- UIS child of the 3x3 Tent controller; devType 10001, devId …710774.
  It does NOT appear in `aci controllers`/`aci status`.
- Sensors: in `aci raw`, the tent device's `ipc` object (×100 ints):
  thermalCenter = leaf temp °C×100 (mirrored in insideTempF), thermalAvg/
  Min/Max, temperatureF, humidity, vpdnums = leaf-aware VPD.
- **Photos — `aci-photos` is the whole job.** It queries the cloud photo log
  correctly. Rules baked into the tool, don't re-derive them by hand:
  the API only answers DAY-ALIGNED windows (one calendar day per query);
  a multi-day window silently returns []. Categories overlap — the tool
  dedupes. Records carry signed `downloadUrl`s (7-day expiry).
  Manual captures from the app DO upload; both the main 4K camera and the
  under-canopy camera land in the same log.
- If `aci-photos` shows nothing but the author says photos exist: the log's
  date index is POST /api/ipc/photoLogsDate (see SPECTRON-IPC.md next to
  this skill for the full contract) — a non-empty date list means photos
  exist for that day.
- Settings writes from the API do NOT work — root-caused 2026-11-16:
  the cloud write path is auxiliary/legacy (only a server-owned display
  preference succeeds; camera-executed settings return 500/999999) and
  the app's real settings UI syncs settings to the camera over P2P.
  If the author wants timed photos changed, he flips it in the AC Infinity
  app; you pull the results.
- **Timed photos are ON and verified** (2026-11-16): the author armed them in
  the app and unattended shots land in the cloud log ~hourly. The cloud
  settings record still reads autoPhotoStatus 0 — ignore it; photos
  landing is the proof.
- An MCP server for these tools is registered in your config as
  `ac-infinity` (~/ac-infinity-tools/mcp/server.py): tools aci_status,
  spectron_sensors, spectron_photos, and spectron_snapshot — all live.
- **On-demand snapshots WORK (solved 2026-11-16).** The MCP
  `spectron_snapshot` tool boots an ephemeral Android-emulator rig on
  this Mac that runs the vendor's own camera library with the app's
  exact call sequence (a hand-reimplemented protocol client was refused
  by the vendor's servers; the genuine library's session orchestration
  — a composite credential string — was the missing piece). It returns
  a main-camera still (3840×2160) and a sub-camera still (1920×1080)
  in ~1–5 min including rig boot. Know: SDK stills are session-only
  and do NOT appear in the cloud photo log; the sub camera has no IR,
  so its night stills are near-black; a call occasionally stalls at
  connect and returns {available:false, status:"failed", detail:…}
  with diagnostics saved — report that honestly rather than retrying
  in a loop.
- Full dossier (endpoint table, traps, P2P state): SPECTRON-IPC.md in this
  same skill folder.

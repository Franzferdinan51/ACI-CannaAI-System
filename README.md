# ACI-CannaAI-System

**A complete AC Infinity automation system — controllers, cameras, a live
data feed, and AI-agent access — reverse-engineered and open.**

This is the whole stack that runs a real home grow room, published so anyone
with AC Infinity gear can build the same thing:

- **Monitor everything.** Controllers (temperature, humidity, VPD, every
  port and device) *and* the Spectron camera's own sensors — including
  **leaf temperature and leaf VPD** from its thermal sensor, numbers the
  official app barely surfaces.
- **Control the room.** Port modes and values, the controller AI program,
  schedules — the full unofficial cloud API, wrapped in one CLI.
- **See the plants.** Pull the Spectron's cloud photos programmatically
  (timed shots included), on a schedule, into your own pipeline.
- **Feed your software.** A 10-minute collector keeps a local JSON feed
  fresh for dashboards and automations.
- **Let an agent run it.** An MCP server plus ready-made agent skills (the
  exact playbooks two different AI agents operate this system with) — the
  "CannaAI" half: twice-daily automated grow checks that combine probe
  readings, leaf readings, and camera photos, and flag disease or pests.

## Best used in conjunction with CannaAI

This repo is the hardware and data layer. It is **best used in conjunction
with [CannaAI](https://github.com/Franzferdinan51/CannaAI)** — the grow
assistant that consumes this system's feed, sensors, and camera photos to
do computer-vision plant diagnosis, grow journaling, tent monitoring, and
breeding tracking. The ACI system keeps CannaAI's eyes and hands in the
tent; CannaAI is the brain that turns the readings into decisions. Each
works alone, but they were built for each other and run together in
production.

The cameras were the undocumented part. Every public AC Infinity project
covers controllers; the Spectron 3/7 had **zero** public API documentation
— no endpoints, no photo access, nothing. The camera half of this repo
(cloud IPC API + CS2 P2P reverse engineering) was built from a jadx
decompile of the official Android app and live protocol work. See
[docs/SPECTRON-IPC.md](docs/SPECTRON-IPC.md).

## What works today

| Capability | How |
|---|---|
| Controller status (temp / RH / VPD / ports / devices) | `tools/aci.py status` |
| Controller writes (port mode/value, AI program, schedules) | `tools/aci.py` — see the safety note |
| Camera sensors — **leaf temp, leaf VPD**, thermal min/avg/max | the `ipc` object in the raw device list, or MCP `spectron_sensors` |
| **Pull camera photos from the cloud** | `tools/aci-photos.py` (read the day-window warning below) |
| Timed photos | arm Auto Photo in the official app once; pull results with `aci-photos` |
| On-demand photos — fallback route | drive the official app over ADB (requires a phone connected): screencap the live view; tap the picture-in-picture preview to swap to the side camera, Refresh, screencap again |
| Always-fresh local data feed | `tools/acinfinity-apifeed.py` + `macos/com.example.acinfinity-collect.plist` (every 10 min) |
| Legacy app-scrape fallback | `tools/acinfinity-collect.sh` (ADB, manual use) |
| Agent access (MCP, stdio, zero dependencies) | `mcp/server.py` — `aci_status`, `spectron_sensors`, `spectron_photos` |
| Agent playbooks | `skills/juno/SKILL.md`, `skills/hermes/SKILL.md` |

## What's settled — and what's still open

- **On-demand snapshots: no phone-free trigger exists in this system's
  design (verified 2026-11-16).** A full dig worked every remaining
  route. The app's Take Photo button is a local grab of the rendered
  stream frame — no cloud call, no camera command; the camera's true
  still capture (HD photo mode) sends `JSON_CMD_SNAPSHOT_IMG` (48) over
  the P2P session only. Live view starts with no session-authorization
  cloud call (its only cloud calls are the SDK init string, P2P info,
  server IP, and settings reads). The controller exposes no camera
  trigger surface, and Bluetooth control reaches only the controller's
  climate loads — the camera is not a Bluetooth peripheral. The two
  capture triggers that exist are the device-side timer (phone-free,
  harvested by `aci-photos`) and the P2P snapshot command below. The
  working on-demand fallback requires a phone running the official app,
  driven over ADB — open the camera page and screencap the live view
  for the main camera; tap the picture-in-picture preview to swap to
  the side (under-canopy) camera, hit Refresh, and screencap again.
  Screen-resolution frames, but truly on-demand, both cameras.
  Full evidence: the "Phone-free trigger dig" section of
  [docs/SPECTRON-IPC.md](docs/SPECTRON-IPC.md).
- **Native P2P snapshots.** The camera speaks a CS2-networks P2P
  protocol with a proprietary TCP rendezvous. The login handshake is
  **cracked and reproduced byte-for-byte** (see `p2p-research/`), and the
  relay-session-start packet (`TCPRSStart`) has since been reconstructed
  byte-for-byte too, along with every variant the vendor SDK can emit —
  all of them live-tested, including during a co-test with the official
  app's live view streaming. The data phase after the handshake still
  refuses every one of them; the blocker is provably not any client
  packet. `JSON_CMD_SNAPSHOT_IMG` (command 48) is identified and
  waiting. The MCP server carries `spectron_snapshot` as an
  experimental stub; a future vendor firmware/app change adding a
  cloud capture endpoint is the only known path left.
- **Cloud settings writes** (`/api/ipc/setting`) are auxiliary/legacy:
  the write repository is wired only into the app's plant-AI screens,
  and the real settings UI executes over the P2P channel. Live-tested:
  camera-executed settings fail downstream (500) or fail validation
  (999999); the one write that returns 200 is a server-owned display
  preference. Root cause and the full probe matrix are in the dossier.

## ⚠️ The one trap that will waste your evening

`POST /api/ipc/photoLogs` **only answers day-aligned windows** — one
calendar day per query (`startTime` = local midnight in epoch seconds,
`endTime = startTime + 86399`). Ask for a wider window and it silently
returns `[]` even when photos exist. Categories are overlapping filters,
not partitions — dedupe by `photoTime`. Full contract:
[docs/SPECTRON-IPC.md](docs/SPECTRON-IPC.md).

## Setup

You need: Python 3.9+, an AC Infinity account, and your own gear.

```bash
# 1. Log in — prompts for your account email + password, stores ONLY the
#    resulting token at ~/.config/aci/token.json (mode 600).
python3 tools/aci-login.py

# 2. Find your device IDs.
python3 tools/aci.py controllers     # controllers
python3 tools/aci.py raw             # the camera is the `ipc` object inside
                                     # your tent controller — copy its devId

# 3. Point the camera tools at YOUR camera.
export ACI_CAMERA_DEV_ID=<your camera devId>
export ACI_TENT_DEV_ID=<your controller devId>   # only for tools/ml-pause.py

# 4. Use it.
python3 tools/aci.py status
python3 tools/aci-photos.py --days 2 --download ~/spectron-photos

# 5. (Optional, macOS) keep the data feed fresh: edit the paths in
#    macos/com.example.acinfinity-collect.plist to your install, copy it to
#    ~/Library/LaunchAgents/, and `launchctl load` it.
```

**Your token is full account access.** It lives in
`~/.config/aci/token.json` — never commit it, never share it. (It's in
`.gitignore` here on purpose.) Every ID in this repo is a placeholder for
the same reason: the published code was scrubbed of the original system's
real device IDs, and yours stay yours.

## MCP server

Pure-stdlib stdio MCP server — point any MCP client at it:

```json
{
  "mcpServers": {
    "ac-infinity": {
      "command": "python3",
      "args": ["/path/to/ACI-CannaAI-System/mcp/server.py"],
      "env": { "ACI_CAMERA_DEV_ID": "<your camera devId>" }
    }
  }
}
```

See [mcp/README.md](mcp/README.md) for the tool list and protocol notes.

## Layout

- `tools/` — `aci.py` (controllers + raw API), `aci-photos.py` (photo log
  pulls), `aci-login.py` (token setup), `acinfinity-apifeed.py` (the local
  data feed), `acinfinity-collect.sh` (legacy ADB scrape fallback),
  `ml-pause.py` (pause helper for the grow dashboard).
- `mcp/` — the MCP server (`server.py`; `p2p_client.py` is the snapshot
  client's drop-in slot).
- `skills/` — the agent playbooks this system is actually operated with:
  the full operations skill (`juno/`) and a second agent's variant
  (`hermes/`). Start with these if you want an AI running your room.
- `macos/` — the LaunchAgent that runs the data feed every 10 minutes.
- `docs/SPECTRON-IPC.md` — the full camera dossier: endpoints, auth, traps,
  settings command codes, P2P state.
- `docs/spectron-research-report.md` — the research pass behind the camera
  work: what exists publicly (nothing), the Spectron 3/7 platform identity,
  and how the P2P stack was identified.
- `p2p-research/` — the P2P reverse-engineering trail: notes, the DevLgn/relay
  spec, extracted crypto tables, SDK emulation scripts (`emu*.py`), and the
  live probe stages (`stage*.py`). Research code — it hardcodes nothing of
  yours; set `ACI_CAMERA_DEV_ID` and it fetches your own P2P info at runtime.

## Safety

The read paths are safe to run anytime. The controller **write** commands
change real grow equipment (lights, fans, humidifiers) — a wrong change
costs plants, not tokens. Use them deliberately.

## Credits

Built by **Franzferdinan51** and **Juno** (his AI agent), 2026, against
their own gear and account. Protocol facts about the vendor SDK
(init-string table, session S-box, directory servers) were extracted from
the official Android app.

This project also stands on earlier community work on AC Infinity's
unofficial cloud API — all of it controller-focused, and all of it worth
your time if you run these controllers:

- **[dalinicus/homeassistant-acinfinity](https://github.com/dalinicus/homeassistant-acinfinity)**
  — the Home Assistant integration; its API client was the reference this
  project's `aci` tooling was first built against. (Its issue #156 is an
  open request for Spectron video support — the camera work in this repo
  is, as far as we can tell, the first public answer to it.)
- **[ober37/ac-infinity-mcp](https://github.com/ober37/ac-infinity-mcp)**
  — an MCP server for the controllers with the most complete public
  write-up of the cloud API (`docs/API.md`).
- **joshuaseidel's fork** of the Home Assistant integration — its AI+
  controller data reference (100+ data points) helped map the AI-program
  settings.

The Spectron camera half — the `/api/ipc/` cloud endpoints, the photo
pulls, and the CS2 P2P reverse engineering — had no public prior work to
build on and is original to this repo.

## License

MIT — see [LICENSE](LICENSE).

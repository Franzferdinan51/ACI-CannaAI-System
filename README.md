# ACI-CannaAI-System

**The AC Infinity camera API nobody documented — reverse-engineered, tooled, and open.**

Every public AC Infinity project covers *controllers*. The Spectron cameras
(3 and 7) had **zero** public API documentation — no endpoints, no photo
access, nothing. This repo is the system built by pulling a Spectron 7 apart
at the protocol level: the unofficial cloud IPC API, the camera's CS2 P2P
protocol, working command-line tools, and an MCP server so an AI agent can
run the grow room.

Built for a real home grow (the "CannaAI" half — twice-daily automated plant
checks with leaf temperature and leaf-VPD from the camera's thermal sensor),
but everything here works for anyone with AC Infinity gear and an account.

## What works today

| Capability | How |
|---|---|
| Controller status (temp / RH / VPD / ports) | `tools/aci.py status` |
| Camera sensors — **leaf temp, leaf VPD**, thermal min/avg/max | the `ipc` object in the raw device list, or the MCP `spectron_sensors` tool |
| **Pull camera photos from the cloud** | `tools/aci-photos.py` (read the day-window warning below) |
| Timed photos | arm Auto Photo in the official app once; pull the results with `aci-photos` |
| Agent access (MCP, stdio, zero dependencies) | `mcp/server.py` — `aci_status`, `spectron_sensors`, `spectron_photos` |

## What's still being cracked

- **On-demand snapshots over P2P.** The camera speaks a CS2-networks P2P
  protocol with a proprietary TCP rendezvous. The login handshake is
  **cracked and reproduced byte-for-byte** (see `p2p-research/`); the data
  phase after the handshake is the open problem. `JSON_CMD_SNAPSHOT_IMG`
  (command 48) is identified and waiting. The MCP server carries
  `spectron_snapshot` as an experimental stub until this lands — when it
  does, this repo gets updated.
- **Cloud settings writes** (`/api/ipc/setting`) return HTTP 500 for every
  app-shaped request tried. The app also syncs settings to the camera over
  its P2P channel, which is likely the missing half.

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
  pulls), `aci-login.py` (token setup), plus the CannaAI dashboard feed and
  pause helpers the original system runs on.
- `mcp/` — the MCP server (`server.py`, `p2p_client.py` is the snapshot
  client's drop-in slot).
- `docs/SPECTRON-IPC.md` — the full camera dossier: endpoints, auth, traps,
  settings command codes, P2P state.
- `p2p-research/` — the P2P reverse-engineering trail: notes, the DevLgn/relay
  spec, extracted crypto tables, SDK emulation scripts (`emu*.py`), and the
  live probe stages (`stage*.py`). Research code — it hardcodes nothing of
  yours; set `ACI_CAMERA_DEV_ID` and it fetches your own P2P info at runtime.

## Safety

The read paths are safe to run anytime. The controller **write** commands in
`aci.py` change real grow equipment (lights, fans, humidifiers) — a wrong
change costs plants, not tokens. Use them deliberately.

## Credits

Reverse engineering, tools, and docs by **Franzferdinan51** and **Juno**
(his AI agent), November 2026, against their own camera and account.
Protocol facts about the vendor SDK (init-string table, session S-box,
directory servers) were extracted from the official Android app.

## License

MIT — see [LICENSE](LICENSE).

# ac-infinity MCP server

A Model Context Protocol (MCP) server for the author' AC Infinity gear — the
3x3 Tent / Clone Chamber controllers and the Spectron 7 camera — speaking
to the AC Infinity cloud API (`https://www.acinfinityserver.com`, the same
unofficial API the mobile app uses).

**Read-only.** Every tool only reads. There are no control/write tools.

**Zero dependencies.** Pure Python standard library — the MCP stdio
handshake (JSON-RPC 2.0, newline-delimited) is implemented in `server.py`
itself, and cloud calls use `urllib`. Any `python3 >= 3.9` runs it,
including the macOS system python. See `requirements.txt` (it's empty on
purpose).

Full API dossier (endpoint contract, photo-window traps, P2P state):
`../SPECTRON-IPC.md`.

## Files

| File | What |
|---|---|
| `server.py` | The MCP server (self-contained at runtime). |
| `p2p_client.py` | On-demand snapshot rig: boots an ephemeral Android emulator on the Mac, runs the vendor's own SDK via the harness in `rig/harness/`, captures main + sub stills. Credentials are fed in-process only. |
| `rig/harness/` | The GQ harness (APK sources + build.sh + credential feeder) driven by `p2p_client.py`. Full recipe: `../../spectron-pppp/harness/README.md`. |
| `tests/test_mcp.py` | Stdio test client: initialize + tools/list + tools/call, prints responses. |

## Auth

Header `token` = the `user_id` value in the token file, read at runtime on
every call (never printed or logged):

- env `ACI_TOKEN_FILE`, default `~/.config/aci/token.json`
- Create/refresh it with `aci-login` (interactive; stores only the token).

## Run

```sh
python3 server.py            # speaks MCP on stdin/stdout; logs to stderr
```

Smoke test (needs a valid token file — on the Mac it just works):

```sh
python3 tests/test_mcp.py                 # all four tools
python3 tests/test_mcp.py spectron_sensors
```

## Tools

### `aci_status` — no arguments
All controllers: inside/outside readings (temp °F, %RH, VPD) + each port's
name, level (`speak`) and on/off state — mirrors `aci status`, including
the AI-program line on AI controllers. Returns text + `structuredContent`
(`controllers[]` with `readings`, `ports`, `sensors`).

### `spectron_sensors` — optional `dev_id`
The Spectron 7's sensor snapshot from the `ipc` object inside
`devInfoListAll` (fields are ×100 ints), in human units: thermal center
(= leaf temp), avg / min / max in °C and °F, air temp, humidity, leaf VPD,
plus sensor-online flags and the parent controller's name.

### `spectron_photos` — `days` (default 1, max 31), `download_dir` (optional), `dev_id` (optional)
Cloud photo log for the camera. The API only answers **day-aligned
windows** (one calendar day per query; wide windows silently return
`[]`), and categories 0–5 overlap, so the tool queries per-day ×
categories 0–5 and dedupes by `photoTime`. Returns the record list
(`photoTime` epoch + ISO in ET and UTC, signed `downloadUrl` — 7-day
expiry, `thumbsUrl`, `rid`). With `download_dir`, JPEGs are downloaded as
`spectron-<photoTime>.jpg` and each record gains a `localPath`.

### `spectron_snapshot` — `dev_id` (optional), `download_dir` (optional)
On-demand snapshot, solved 2026-11-16: a hand-reimplemented P2P client
was refused by the vendor's relay servers, but the vendor's own SDK
library connects — so this tool runs that library. It boots an
ephemeral Android emulator rig (RAM disk; the Mac's disks are nearly
full), replays the app's exact SDK call sequence with the composite
credential `intstr + ":" + key` (fetched in-process from `getP2PInfo`,
never persisted), and captures a main still (3840×2160, ~2 MB) plus a
sub-camera still (1920×1080). The rig is torn down afterwards; nothing
is left running. Slow: ~1–5 min including rig setup and boot. Returns
local JPEG paths, byte counts, dimensions, the exact SDK return codes,
and phase timings; failures return `{available: false,
status: "failed", detail: …}` with the failing step and SDK codes.
SDK-triggered stills are session-only — they do not appear in the
cloud photo log (`spectron_photos`).

## Hermes registration (Mac)

Hermes reads stdio servers from the `mcp_servers:` section of
`~/.hermes/config.yaml` (same shape as the existing stdio entries, e.g.
`mlx-lm-lora` / the historical `rea` entry). The registered entry:

```yaml
mcp_servers:
  ac-infinity:
    command: /usr/bin/python3
    args:
      - /Users/YOURNAME/ac-infinity-tools/mcp/server.py
    enabled: true
```

On the Mac the server lives at `~/ac-infinity-tools/mcp/` (same layout as
here) and the token at `~/.config/aci/token.json` is the default path, so
no env needs setting. Restart Hermes after editing the config for it to
pick the server up.

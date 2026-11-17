"""p2p_client — drop-in slot for the Spectron 7 P2P snapshot client.

Ships as a stub, but not for lack of a client: the protocol is fully
reverse-engineered — the rendezvous handshake and the TCPRSStart
relay-session packet are reproduced byte-for-byte (see p2p-research/) —
and the vendor's directory/relay servers currently refuse every
data-phase packet after the handshake, so JSON_CMD_SNAPSHOT_IMG is
unreachable for now. When that opens, the real client (TCP RlyReq ->
RlyRdy -> TCPRSStart -> JSON_CMD_SNAPSHOT_IMG, per SPECTRON-IPC.md)
replaces the body of snapshot() and the MCP tool `spectron_snapshot`
starts working with no server changes.

Contract for the future implementation:
  snapshot(dev_id) -> dict with at least:
      {"path": <local jpeg path>, "bytes": <int>, "taken_at": <iso str>}
  It must fetch P2P credentials via the cloud API at runtime and must
  never log or return them.
"""
from __future__ import annotations


class P2PNotAvailable(Exception):
    """Raised while the vendor's servers refuse the P2P data phase."""


def snapshot(dev_id, dest_dir=None):
    raise P2PNotAvailable(
        "experimental: P2P snapshot not yet available "
        "(client implemented + verified byte-for-byte; the vendor's "
        "relay servers refuse the post-handshake data phase)"
    )

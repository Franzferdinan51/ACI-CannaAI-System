"""p2p_client — drop-in slot for the Spectron 7 P2P snapshot client.

Phase 2 thread B ships this as a stub. The real implementation (TCP DevLgn
with DSK -> relay -> JSON_CMD_SNAPSHOT_IMG, per SPECTRON-IPC.md) lands in a
later phase: replace the body of snapshot() with the real client and the
MCP tool `spectron_snapshot` starts working with no server changes.

Contract for the future implementation:
  snapshot(dev_id) -> dict with at least:
      {"path": <local jpeg path>, "bytes": <int>, "taken_at": <iso str>}
  It must fetch P2P credentials via the cloud API at runtime and must
  never log or return them.
"""
from __future__ import annotations


class P2PNotAvailable(Exception):
    """Raised while the P2P snapshot path is not implemented yet."""


def snapshot(dev_id, dest_dir=None):
    raise P2PNotAvailable(
        "experimental: P2P snapshot not yet available "
        "(TCP DevLgn/relay client not implemented yet)"
    )

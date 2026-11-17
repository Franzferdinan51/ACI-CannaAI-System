#!/usr/bin/env python3
"""test_mcp — exercise the ac-infinity MCP server over stdio.

Spawns server.py, sends initialize + notifications/initialized +
tools/list + tools/call for each tool named on the command line
(default: spectron_sensors spectron_photos spectron_snapshot aci_status),
and prints every response as pretty JSON. Exit code 0 only if initialize
succeeds, tools/list contains all four tools, and no requested call
returns a JSON-RPC error.

Usage: python3 test_mcp.py [tool ...]
Env:   MCP_SERVER_PYTHON (default: sys.executable),
       MCP_SERVER_PATH (default: ../server.py relative to this file)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.environ.get("MCP_SERVER_PATH", os.path.join(HERE, "..", "server.py"))
PYTHON = os.environ.get("MCP_SERVER_PYTHON", sys.executable)
EXPECTED_TOOLS = {"aci_status", "spectron_sensors", "spectron_photos",
                  "spectron_snapshot"}


def main():
    calls = sys.argv[1:] or ["spectron_sensors", "spectron_photos",
                             "spectron_snapshot", "aci_status"]
    proc = subprocess.Popen(
        [PYTHON, SERVER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    seq = [0]

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def request(method, params=None):
        seq[0] += 1
        send({"jsonrpc": "2.0", "id": seq[0], "method": method,
              "params": params or {}})
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout on %s" % method)
        resp = json.loads(line)
        print("=== %s ->" % method)
        print(json.dumps(resp, indent=1)[:4000])
        return resp

    ok = True
    init = request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test_mcp", "version": "1.0"},
    })
    if "result" not in init:
        ok = False
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    listing = request("tools/list")
    names = {t["name"] for t in listing.get("result", {}).get("tools", [])}
    print("tools/list names:", sorted(names))
    if names != EXPECTED_TOOLS:
        print("FAIL: expected %s" % sorted(EXPECTED_TOOLS))
        ok = False

    args_for = {
        "aci_status": {},
        "spectron_sensors": {},
        "spectron_photos": {"days": 2},
        "spectron_snapshot": {},
    }
    for name in calls:
        resp = request("tools/call", {"name": name,
                                      "arguments": args_for.get(name, {})})
        if "error" in resp:
            print("FAIL: %s returned a JSON-RPC error" % name)
            ok = False

    proc.stdin.close()
    proc.wait(timeout=10)
    err = proc.stderr.read()
    if err.strip():
        print("--- server stderr ---")
        print(err[:2000])
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

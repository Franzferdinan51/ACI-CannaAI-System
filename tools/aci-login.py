#!/usr/bin/env python3
"""One-time AC Infinity login for the aci tool.

Run in a Terminal on the Mac:  ~/bin/aci-login
Prompts for the AC Infinity account email + password, exchanges them for
the account token, and saves ONLY the token to ~/.config/aci/token.json
(mode 600). The password is never stored or logged.

Note: AC Infinity's own API truncates passwords to 25 characters (the app
does the same), so that is what gets sent.
"""
import getpass
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://www.acinfinityserver.com"
TOKEN_PATH = os.path.expanduser("~/.config/aci/token.json")


def post(path, data, token=None):
    headers = {"User-Agent": "okhttp/4.12.0"}
    if token:
        headers["token"] = token
    body = urllib.parse.urlencode(data).encode()
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main():
    email = input("AC Infinity email: ").strip()
    password = getpass.getpass("AC Infinity password (hidden): ")
    try:
        body = post(
            "/api/user/appUserLogin",
            {"appEmail": email, "appPasswordl": password[:25]},
        )
    except Exception as exc:
        print("login request failed: %s" % exc)
        return 1
    if body.get("code") != 200 or not (body.get("data") or {}).get("appId"):
        print("login failed: %s" % json.dumps(body)[:200])
        return 1
    user_id = body["data"]["appId"]
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as fh:
        json.dump({"user_id": user_id, "email": email}, fh)
    os.chmod(TOKEN_PATH, 0o600)
    print("token saved to %s (password NOT stored)" % TOKEN_PATH)
    try:
        lst = post("/api/user/devInfoListAll", {"userId": user_id}, token=user_id)
        names = [c.get("devName") for c in (lst.get("data") or [])]
        print("controllers on this account: %s" % ", ".join(names))
    except Exception as exc:
        print("logged in, but controller list failed: %s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
dotgg_login.py — One-time DotGG login.
Speichert DOTGG_USER_ID + DOTGG_TOKEN in .env (overwrites both keys if present).

Usage:
    python3 dotgg_login.py
    python3 dotgg_login.py --email foo@bar.com   # password aus interactive prompt

Erfordert getpass für sichere Passwort-Eingabe.
"""

import argparse
import getpass
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
ENV_FILE = REPO / '.env'
AUTH_URL = 'https://api.dotgg.gg/email-auth-mobile.php'


def login(user, password):
    data = urllib.parse.urlencode({'email': user, 'password': password}).encode()
    req = urllib.request.Request(
        AUTH_URL, data=data, method='POST',
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'DotGG/2.0 (Mobile; iOS)',
            'Accept': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        print(f"⚠️ HTTP {e.code} — Body: {body[:500]}")
        # Try to parse JSON error even on non-200
        try:
            j = json.loads(body)
            if j.get('error'):
                print(f"❌ Server error: {j['error']}")
            return None
        except Exception:
            print(f"❌ Non-JSON error response: {body[:200]}")
            return None
    try:
        j = json.loads(body)
    except Exception:
        print(f"❌ Non-JSON response: {body[:200]}")
        return None
    if j.get('error'):
        print(f"❌ {j['error']}")
        return None
    user_id = j.get('DotGGUser')
    token = j.get('DotGGUserToken')
    if not user_id or not token:
        print(f"❌ Unexpected response: {j}")
        return None
    return str(user_id), token


def upsert_env(updates):
    lines = []
    keys_done = set()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                lines.append(line); continue
            if '=' in stripped:
                key = stripped.split('=', 1)[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    keys_done.add(key)
                    continue
            lines.append(line)
    for k, v in updates.items():
        if k not in keys_done:
            lines.append(f"{k}={v}")
    ENV_FILE.write_text('\n'.join(lines) + '\n')
    ENV_FILE.chmod(0o600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user')
    args = ap.parse_args()

    user = args.user or os.environ.get('DOTGG_USER') or input("DotGG username or email: ").strip()

    # Password: ENV → stdin (wenn pipe) → getpass (interactive)
    password = os.environ.get('DOTGG_PASSWORD')
    if not password:
        if not sys.stdin.isatty():
            password = sys.stdin.readline().rstrip('\n')
        else:
            try:
                password = getpass.getpass("DotGG password (hidden, paste möglich via Strg+V/Cmd+V): ")
            except Exception:
                password = input("DotGG password (sichtbar!): ")

    print("→ Logging in …")
    res = login(user, password)
    if not res:
        return 1
    user_id, token = res
    upsert_env({
        'DOTGG_USER_ID': user_id,
        'DOTGG_TOKEN': token,
        'DOTGG_USER': user,
    })
    print(f"✅ Login OK — user_id={user_id}, token saved to {ENV_FILE} (chmod 600)")
    return 0


if __name__ == '__main__':
    sys.exit(main())

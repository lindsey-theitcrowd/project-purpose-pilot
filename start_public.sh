#!/usr/bin/env bash
# (Re)start the pilot server + a free Cloudflare quick tunnel, then print the private share link.
# DEMO - fictional sample data only.
set -e; cd "$(dirname "$0")"
CF=$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")
[ -s .share_token ] || { umask 077; python3 -c "import secrets;print(secrets.token_urlsafe(32),end='')" > .share_token; }
chmod 600 .share_token
pkill -f "uvicorn app:app --host 127.0.0.1 --port 8765" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:8765" 2>/dev/null || true
sleep 1
[ -f data/pilot_SAMPLE.db ] || .venv/bin/python -m pp.demo --seed >/dev/null
nohup .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765 > server.log 2>&1 &
for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8765/ && break; sleep 0.5; done
: > tunnel.log
nohup "$CF" tunnel --no-autoupdate --url http://127.0.0.1:8765 > tunnel.log 2>&1 &
URL=""
for i in $(seq 1 60); do URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' tunnel.log | head -1); [ -n "$URL" ] && break; sleep 1; done
[ -n "$URL" ] || { echo "Tunnel did not come up; see tunnel.log"; exit 1; }
echo "$URL" > .public_url
echo "Share link: $URL/?k=$(cat .share_token)"

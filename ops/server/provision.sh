#!/usr/bin/env bash
# One-time server setup from your Mac. Usage: ops/server/provision.sh admin@server-address site-hostname
# admin is the login OVHcloud gave you (it needs sudo, or use root). site-hostname is the name the app is
# served on: the hostname OVHcloud gave the server (try `host <server ip>`), else <ip with dashes>.sslip.io.
# Caddy serves HTTPS only; who may sign in is the app's own login (create the admin after the first push).
set -euo pipefail

host=${1:?usage: provision.sh admin@server-address site-hostname}
site_host=${2:?usage: provision.sh admin@server-address site-hostname}
[[ "$site_host" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "site-hostname: letters, digits, dots, hyphens only" >&2; exit 1; }
cd "$(dirname "$0")"

# tar over ssh because a fresh image may not have rsync yet.
tar -cf - . | ssh "$host" 'rm -rf /tmp/fantasy-server && mkdir /tmp/fantasy-server && tar -xf - -C /tmp/fantasy-server'
ssh -t "$host" "if [ \"\$(id -u)\" -eq 0 ]; then SITE_HOST=$site_host bash /tmp/fantasy-server/bootstrap.sh; else sudo env SITE_HOST=$site_host bash /tmp/fantasy-server/bootstrap.sh; fi"

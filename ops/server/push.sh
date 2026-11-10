#!/usr/bin/env bash
# Sends this checkout to the server and restarts the app. Usage: ops/server/push.sh [--data] fantasy@server-address
# --data copies data/ once, on the first deploy. After that the server owns it (its timer runs the refresh),
# so --data refuses to overwrite a server that already has tables.
# shellcheck disable=SC2029 # REMOTE_DIR and REMOTE_UV are constants meant to expand here
set -euo pipefail

copy_data=false
host=""
for arg in "$@"; do
  case "$arg" in
    --data) copy_data=true ;;
    *) host=$arg ;;
  esac
done
[ -n "$host" ] || { echo "usage: push.sh [--data] fantasy@server-address" >&2; exit 1; }

cd "$(dirname "$0")/../.."
REMOTE_DIR=fantasy-app
REMOTE_UV=.local/bin/uv

if $copy_data && ssh "$host" "test -e $REMOTE_DIR/data/current -o -d $REMOTE_DIR/data/derived"; then
  echo "the server already has tables; copying data/ would overwrite its history" >&2
  exit 1
fi

make web-build # the server has no Node, so it serves the UI built here

# Excluded paths are also protected from --delete, so the server's data, venv and .env survive.
rsync -az --delete \
  --exclude .git --exclude .venv --exclude node_modules --exclude __pycache__ \
  --exclude '.*_cache' --exclude /data --exclude .env --exclude research/scratch \
  ./ "$host:$REMOTE_DIR/"

if $copy_data; then rsync -az data/ "$host:$REMOTE_DIR/data/"; fi

ssh "$host" "cd $REMOTE_DIR && ~/$REMOTE_UV sync --frozen --no-dev && sudo systemctl restart fantasy-app"
if ssh "$host" 'for _ in $(seq 30); do curl -fsS -o /dev/null http://127.0.0.1:8000/ && exit 0; sleep 1; done; exit 1'; then
  echo "App is up on the server."
else
  echo "App did not answer on the server; run: ssh $host journalctl -u fantasy-app -n 50" >&2
  exit 1
fi

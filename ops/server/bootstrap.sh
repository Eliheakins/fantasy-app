#!/usr/bin/env bash
# Prepares a fresh Ubuntu 24.04 VPS to run fantasy-app. Run as root, normally through provision.sh.
# Needs SITE_HOST, the public hostname Caddy gets a certificate for. Safe to re-run.
set -euo pipefail

APP_USER=fantasy
APP_HOME=/home/$APP_USER
HERE=$(cd "$(dirname "$0")" && pwd)
TIMEZONE=America/New_York # the app reads local time (_scorecard.py) and the refresh times are Eastern
SWAP_SIZE=2G              # refresh memory use is unmeasured; swap keeps a 4 GB box from being killed

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
[[ "${SITE_HOST:-}" =~ ^[A-Za-z0-9.-]+$ ]] ||
  { echo "set SITE_HOST to the server's hostname (letters, digits, dots, hyphens)" >&2; exit 1; }

# The admin login's keys also become the app user's keys, so push.sh can log in as that user.
admin_keys=""
for candidate in "${SUDO_USER:+/home/$SUDO_USER/.ssh/authorized_keys}" /root/.ssh/authorized_keys; do
  if [ -n "$candidate" ] && [ -s "$candidate" ]; then admin_keys=$candidate; break; fi
done
[ -n "$admin_keys" ] || { echo "no authorized_keys found; add an SSH key to the server first" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl make rsync ufw unattended-upgrades

timedatectl set-timezone "$TIMEZONE"

if ! swapon --show | grep -q .; then
  fallocate -l "$SWAP_SIZE" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

id "$APP_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$APP_USER"
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$APP_HOME/.ssh"
# Merged, not replaced, so a re-run keeps the GitHub deploy key.
touch "$APP_HOME/.ssh/authorized_keys"
keys_tmp=$(mktemp)
sort -u "$admin_keys" "$APP_HOME/.ssh/authorized_keys" >"$keys_tmp"
install -m 600 -o "$APP_USER" -g "$APP_USER" "$keys_tmp" "$APP_HOME/.ssh/authorized_keys"
rm "$keys_tmp"
[ -x "$APP_HOME/.local/bin/uv" ] ||
  runuser -l "$APP_USER" -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
ln -sf "$APP_HOME/.local/bin/uv" /usr/local/bin/uv # on the PATH of a non-interactive ssh command too
# The units make the home read-only except these, so they must exist before the first run.
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$APP_HOME/.cache" "$APP_HOME/fantasy-app-backups"

# FANTASY_AUTH=required: sign-in is demanded even before the first account exists, so a freshly
# deployed public server is locked, not open, until the admin is created (see the last message).
printf 'API_ALLOWED_HOSTS=%s\nFANTASY_AUTH=required\n' "$SITE_HOST" >/etc/fantasy-app.env

if ! command -v caddy >/dev/null; then
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' |
    gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' >/etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

# Caddy only terminates HTTPS and adds headers; who may sign in is the app's own login.
# Inline styles: charts set React `style` attributes. https: images: player headshots. The intent
# body cap stops a large paid-model request before the app buffers it.
CSP="default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
printf '%s {\n\tencode zstd gzip\n\theader {\n\t\tStrict-Transport-Security "max-age=31536000"\n\t\tX-Content-Type-Options nosniff\n\t\tX-Frame-Options DENY\n\t\tReferrer-Policy strict-origin-when-cross-origin\n\t\tContent-Security-Policy "%s"\n\t}\n\trequest_body /api/stat/nlq/intent {\n\t\tmax_size 32KB\n\t}\n\treverse_proxy 127.0.0.1:8000\n}\n' \
  "$SITE_HOST" "$CSP" >/etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable caddy
systemctl restart caddy

# SSH stays open on the public address for push.sh and the GitHub deploy; keys only.
printf 'PasswordAuthentication no\nPermitRootLogin prohibit-password\n' >/etc/ssh/sshd_config.d/10-fantasy.conf
if sshd -t; then systemctl reload ssh; else rm /etc/ssh/sshd_config.d/10-fantasy.conf; fi
ufw allow OpenSSH >/dev/null
ufw allow 80,443/tcp >/dev/null # 80 is for the certificate check and the redirect to https
ufw --force enable >/dev/null

# push.sh restarts the app as the app user; nothing else gets root.
sudoers_tmp=$(mktemp)
echo "$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart fantasy-app" >"$sudoers_tmp"
visudo -cf "$sudoers_tmp" >/dev/null
install -m 440 "$sudoers_tmp" /etc/sudoers.d/fantasy-app
rm "$sudoers_tmp"

install -m 644 "$HERE"/fantasy-app.service "$HERE"/fantasy-refresh.service \
  "$HERE"/fantasy-refresh.timer "$HERE"/fantasy-refresh.path "$HERE"/fantasy-pipeline@.service \
  "$HERE"/fantasy-daily.timer "$HERE"/fantasy-sleeper.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable fantasy-app.service # starts on the first push, once the code is there
systemctl enable --now fantasy-refresh.timer fantasy-refresh.path fantasy-daily.timer \
  fantasy-sleeper.timer

echo "Server ready. Next: ops/server/push.sh --data $APP_USER@$SITE_HOST"
echo "Then create the admin: ssh -t $APP_USER@$SITE_HOST 'cd fantasy-app && uv run --no-dev python -m fantasy.auth create-admin you@example.com'"
echo "The app will be at https://$SITE_HOST. If the browser shows a certificate error, run on the server: journalctl -u caddy -n 50"

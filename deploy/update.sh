#!/usr/bin/env bash
# Pull the latest code, update dependencies and restart the bot.
# Usage (on the VPS):  sudo /var/www/top-gainers-bot/deploy/update.sh
set -euo pipefail

APP_DIR=/var/www/top-gainers-bot
APP_USER=topgainers
SERVICE=topgainers

if [[ $EUID -ne 0 ]]; then
    echo "Please run with sudo: sudo $0" >&2
    exit 1
fi

cd "$APP_DIR"

echo "==> Pulling latest code"
sudo -u "$APP_USER" git pull --ff-only

echo "==> Installing dependencies"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet --no-cache-dir -r requirements.txt

echo "==> Restarting $SERVICE"
systemctl restart "$SERVICE"
sleep 5

if systemctl is-active --quiet "$SERVICE"; then
    echo "✅ Bot is running. Recent logs:"
    journalctl -u "$SERVICE" -n 20 --no-pager
else
    echo "❌ Bot failed to start. Logs:" >&2
    journalctl -u "$SERVICE" -n 50 --no-pager >&2
    exit 1
fi

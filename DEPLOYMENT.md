# Deploying on a VPS

This guide installs the bot in `/var/www/top-gainers-bot` on an Ubuntu or Debian VPS and runs it as a background service. The service starts automatically on boot and restarts if the bot crashes.

The bot connects **out** to Telegram, the exchanges and MongoDB. It doesn't serve a website, so it needs **no open ports**, no domain and no Nginx.

**What you need**
- SSH access to the VPS with a user that can run `sudo`
- Ubuntu 22.04 / 24.04 or Debian 11 / 12 (Python 3.10 or newer)
- Your Telegram bot token and MongoDB connection string (see [README](README.md#setup))

**At a glance**

| Step | What |
|---|---|
| 1 | Install Python and Git |
| 2 | Check the VPS can reach the exchanges |
| 3 | Create a user for the bot |
| 4 | Download the code into `/var/www` |
| 5 | Install the Python packages |
| 6 | Create the `.env` file |
| 7 | Allow the VPS in MongoDB Atlas |
| 8 | Test run |
| 9 | Run it as a service |
| 10 | Check it works in Telegram |

---

## 1. Install Python and Git

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
python3 --version   # must be 3.10 or newer
```

## 2. Check the VPS can reach the exchanges

Some exchanges block certain countries or cloud providers. Check before you install anything else:

```bash
for url in \
  https://fapi.binance.com/fapi/v1/ping \
  https://api.bybit.com/v5/market/time \
  https://contract.mexc.com/api/v1/contract/ping \
  https://api.bitget.com/api/v2/public/time \
  https://api.gateio.ws/api/v4/futures/usdt/contracts/BTC_USDT \
  https://api.telegram.org; do
  printf "%-60s %s\n" "$url" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url")"
done
```

Each line should end in `200` (Telegram may show `302`). If an exchange shows `403`, `451` or `000`, leave it out of `EXCHANGES` in step 6. Binance and Bybit, for example, block US-based servers. For Bybit you can try `BYBIT_HOSTNAME=bybit.eu` instead.

## 3. Create a user for the bot

The bot runs as its own user without login rights. If someone ever found a bug in it, they couldn't touch the rest of your server.

```bash
sudo adduser --system --group --home /var/www/top-gainers-bot --no-create-home topgainers
```

## 4. Download the code into `/var/www`

```bash
sudo mkdir -p /var/www/top-gainers-bot
sudo chown topgainers:topgainers /var/www/top-gainers-bot
sudo -u topgainers git clone https://github.com/Hyacinth-Chidi/Top_Gainers-bot.git /var/www/top-gainers-bot
```

<details>
<summary><b>If the repository is private</b></summary>

GitHub will ask for a username and password, and your normal password won't work. Use a read-only access token instead:

1. On GitHub: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. **Repository access:** only `Top_Gainers-bot`. **Permissions:** Contents → *Read-only*.
3. Clone with the token. Git saves the address, so later updates work without asking again:

```bash
sudo -u topgainers git clone https://YOUR_GITHUB_USERNAME:YOUR_TOKEN@github.com/Hyacinth-Chidi/Top_Gainers-bot.git /var/www/top-gainers-bot
```

</details>

## 5. Install the Python packages

```bash
cd /var/www/top-gainers-bot
sudo -u topgainers python3 -m venv venv
sudo -u topgainers venv/bin/pip install --no-cache-dir --upgrade pip
sudo -u topgainers venv/bin/pip install --no-cache-dir -r requirements.txt
```

## 6. Create the `.env` file

The bot reads its settings from a file named `.env`. `.env.example` is the template, with every option explained.

```bash
cd /var/www/top-gainers-bot
sudo -u topgainers cp .env.example .env
sudo -u topgainers nano .env
```

Fill in at least:

| Variable | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) on Telegram |
| `MONGODB_URL` | MongoDB Atlas → your cluster → **Connect** → **Drivers** |
| `ADMIN_USER_IDS` | Your Telegram user ID, from [@userinfobot](https://t.me/userinfobot) |
| `BIRDEYE_API_KEY` | Optional, for Solana DEX alerts: [birdeye.so](https://birdeye.so/) |
| `EXCHANGES` | Remove any exchange that failed in step 2 |

In `nano`, save with **Ctrl+O**, **Enter**, and exit with **Ctrl+X**. Then make the file readable only by the bot, since it holds your secrets:

```bash
sudo chmod 600 /var/www/top-gainers-bot/.env
```

## 7. Allow the VPS in MongoDB Atlas

Atlas blocks connections from unknown addresses. Find your VPS's public IP:

```bash
curl -4 ifconfig.me
```

In Atlas, go to **Security → Network Access → Add IP Address**, enter that IP and confirm. It can take a minute to apply.

## 8. Test run

Run the bot in the foreground once to catch mistakes:

```bash
cd /var/www/top-gainers-bot
sudo -u topgainers venv/bin/python main.py
```

You should see `✓ Connected to` for each exchange, then `✓ Connected to MongoDB` and `✅ Bot is running!`. Send `/start` to your bot in Telegram. If it replies, press **Ctrl+C** to stop it and continue.

If something fails, see [Troubleshooting](#troubleshooting).

## 9. Run it as a service

```bash
sudo cp /var/www/top-gainers-bot/deploy/topgainers.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now topgainers
sudo systemctl status topgainers
```

`status` should say **active (running)**. Press **q** to exit. From now on the bot starts on boot and restarts within 10 seconds if it crashes.

## 10. Check it works in Telegram

1. Send `/start` to the bot. You should get the welcome message.
2. Send `/alerts` and tap **🔔 Turn alerts on**.
3. Send `/stats_admin`. If your ID is in `ADMIN_USER_IDS`, you'll see the bot's statistics.
4. Follow the logs and wait. Pump and dump alerts need **5 minutes** of price history after each start, so none can arrive sooner:

```bash
journalctl -u topgainers -f
```

Lines like `🚀 PUMP:`, `💥 DUMP:` or `🔥 DAILY SPIKE:` mean alerts are going out. On a quiet market it can take a while for a coin to move 5% in 5 minutes.

---

## Day-to-day commands

| Task | Command |
|---|---|
| Follow live logs | `journalctl -u topgainers -f` |
| Last 100 log lines | `journalctl -u topgainers -n 100 --no-pager` |
| Status | `sudo systemctl status topgainers` |
| Restart (e.g. after editing `.env`) | `sudo systemctl restart topgainers` |
| Stop | `sudo systemctl stop topgainers` |
| Start | `sudo systemctl start topgainers` |
| Edit settings | `sudo -u topgainers nano /var/www/top-gainers-bot/.env`, then restart |

## Updating to a new version

After new code is merged into `main` on GitHub, run:

```bash
sudo /var/www/top-gainers-bot/deploy/update.sh
```

The script pulls the latest code, installs any new packages, restarts the bot and shows the recent logs. It stops with an error and shows the logs if the bot fails to start.

If `deploy/topgainers.service` itself changes in an update, also run:

```bash
sudo cp /var/www/top-gainers-bot/deploy/topgainers.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart topgainers
```

## Firewall

The bot needs no inbound ports. If you use `ufw`, just keep SSH open:

```bash
sudo ufw allow OpenSSH
sudo ufw enable
```

Outgoing HTTPS (port 443) must be allowed, which is the default.

## Troubleshooting

| Problem | Fix |
|---|---|
| `TELEGRAM_BOT_TOKEN is required` / `MONGODB_URL is required` | `.env` is missing or not filled in. Check it's at `/var/www/top-gainers-bot/.env` (not `.env.example`). |
| `Conflict: terminated by other getUpdates request` | The bot is running somewhere else with the same token, e.g. your own computer. Stop the other copy. Only one may run at a time. |
| `MongoDB connection failed` / timeouts | Add the VPS IP in Atlas (step 7). URL-encode special characters in the password (`@` → `%40`, `#` → `%23`). |
| `Error fetching from binance` (or another exchange) | The exchange blocks your VPS's location. Remove it from `EXCHANGES` in `.env` and restart. |
| `Permission denied` on `.env` or the folder | Ownership is wrong. Run `sudo chown -R topgainers:topgainers /var/www/top-gainers-bot`. |
| `fatal: detected dubious ownership` from git | Run git as the bot user: `sudo -u topgainers git ...`, or use `deploy/update.sh`. |
| Bot replies, but no alerts arrive | Turn alerts on with `/alerts`, check **Alert types** and **Exchanges**, and wait at least 5 minutes after a restart. |
| No DEX alerts | Set `BIRDEYE_API_KEY` in `.env` and restart. |
| Service keeps restarting | Run `journalctl -u topgainers -n 100 --no-pager` and read the first error. |

## Uninstall

```bash
sudo systemctl disable --now topgainers
sudo rm /etc/systemd/system/topgainers.service
sudo systemctl daemon-reload
sudo rm -rf /var/www/top-gainers-bot
sudo deluser --system topgainers
```

Your data stays in MongoDB Atlas until you delete the database there.

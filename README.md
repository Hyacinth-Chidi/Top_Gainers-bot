# Top Gainers Telegram Bot

A Telegram bot that tracks USDT perpetual futures across major crypto exchanges, shows the top gainers and losers on demand, and sends real-time pump and dump alerts. It can also watch Solana DEX trading for big buys.

## Features

- 📊 **Top Gainers & Losers**: Top 5/10/20 movers on Binance, Bybit, MEXC, Bitget and Gate.io, per exchange or all combined, with direct trading links
- 🔮 **Early Pump Signals**: A 0–100 score built from trading volume, momentum, short-term price moves, the daily trend and order book buy pressure
- 🚀 **Pump & 💥 Dump Alerts**: A coin moves ±5% within 5 minutes
- 🔥 **Daily Gainers / 📉 Losers**: A coin is up or down 30–70% on the day (adjustable)
- 🌐 **Solana DEX Alerts**: Big buys and whale buys with wallet links, plus demand spikes (optional, needs a Birdeye API key)
- ⭐ **Watchlist**: Alerts for your coins are flagged and reach you from every exchange, before anyone else
- 🎚️ **Per-user settings**: Turn each alert type on or off and choose which exchanges to hear from
- 🛡️ **Admin tools**: Broadcast, statistics, ban and unban

## How Alerts Work

The bot scans every exchange every `SPIKE_CHECK_INTERVAL` seconds (60 by default) and keeps a short price history in memory.

| Alert | Trigger | Repeats |
|---|---|---|
| 🔮 Early pump | Pump score ≥ 50 while the price is rising (≥ 70 = high confidence) | At most every 30 min per coin |
| 🚀 Pump | +5% within 5 minutes | Every 1h per coin, or sooner if it climbs another 5% past the last alert |
| 💥 Dump | −5% within 5 minutes | Every 1h per coin, or sooner if it falls another 5% past the last alert |
| 🔥 Daily gainer | +30% to +70% over 24h | At most every 12h per coin |
| 📉 Daily loser | −30% to −70% over 24h (off by default) | At most every 12h per coin |
| 🌐 DEX big buy | Single Solana buy ≥ $5k (🐋 ≥ $25k) | Once per transaction |
| 🌐 DEX demand | ≥ 10 buyers and twice as many buyers as sellers | At most every 2h per token |

- **Pump and dump alerts are never held back** by other alerts for the same coin, because timing matters. A daily alert is skipped if the coin was alerted for any reason in the last 30 minutes.
- **Order book "Sniper Mode"**: when a coin scores 20–49, the bot subscribes to its live order book (Binance and MEXC) so buy pressure counts toward the next score.
- **Delivery**: alerts are sent in parallel batches of 25 per second, just under Telegram's limit. People who have the coin on their watchlist get it first.
- **Alerts are off by default.** Users switch them on with `/alerts`. Users who block the bot have their alerts switched off automatically.

## Tech Stack

- **Python 3.11+**
- **python-telegram-bot 21.0** - Telegram Bot API
- **CCXT 4.2.25** - Unified exchange API
- **websockets 12** - Live order book streams
- **httpx** - Birdeye (Solana DEX) API
- **Motor 3.3.2** - Async MongoDB driver
- **MongoDB** - Users, settings, watchlists, alert history

## Project Structure

```
top-gainers-bot/
├── bot/
│   ├── handlers.py          # Command & button handlers
│   ├── keyboards.py         # Inline keyboards
│   ├── messages.py          # Message templates
│   └── utils.py             # Markdown escaping, price formatting, safe sending
├── database/
│   └── client.py            # MongoDB client (users, prefs, watchlists, alert history)
├── dex/
│   └── solana.py            # Birdeye API client (Solana DEX trades & wallets)
├── exchanges/
│   ├── client.py            # Exchange API wrapper (CCXT) with a short ticker cache
│   └── websocket_client.py  # Order book streams ("Sniper Mode": Binance + MEXC)
├── monitoring/
│   ├── broadcaster.py       # Delivers alerts (prefs, bans, watchlists, rate limits)
│   ├── dex_tracker.py       # Solana big-buy / demand alerts
│   └── tracker.py           # Pump, dump & early-signal detection
├── tests/                   # Unit tests (pytest)
├── config.py                # Configuration from environment variables
├── main.py                  # Application entry point
├── requirements.txt         # Dependencies
├── .env.example             # Environment template
└── IMPROVEMENTS.md          # Roadmap
```

## Setup

### 1. Prerequisites

- Python 3.11 or higher
- A MongoDB database (MongoDB Atlas free M0 cluster works)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Optional: a free [Birdeye](https://birdeye.so/) API key for Solana DEX alerts

### 2. Install

```bash
cd top-gainers-bot

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. MongoDB Atlas

1. Create a free account at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) and an **M0 Free Cluster**
2. Under "Security" → "Database Access", create a database user
3. Under "Security" → "Network Access", add your server's IP (or 0.0.0.0/0 for testing)
4. Click "Connect" and copy the connection string, filling in your username and password

```
mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

If your password contains special characters, URL-encode them (`@` → `%40`, `#` → `%23`, `:` → `%3A`).

The bot creates its collections and indexes automatically on first start.

### 4. Telegram Bot Token

1. Message [@BotFather](https://t.me/BotFather) and send `/newbot`
2. Follow the instructions and copy the token

### 5. Configure

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | | Token from @BotFather |
| `MONGODB_URL` | ✅ | | MongoDB connection string |
| `SPIKE_CHECK_INTERVAL` | | `60` | Seconds between market scans (lower = faster alerts, more API calls) |
| `MIN_SPIKE_THRESHOLD` | | `30` | Daily gainer/loser band, lower bound (%) |
| `MAX_SPIKE_THRESHOLD` | | `70` | Daily gainer/loser band, upper bound (%) |
| `EXCHANGES` | | all five | Exchanges to scan for alerts, comma-separated |
| `BYBIT_HOSTNAME` | | `bybit.com` | Bybit region: `bybit.com`, `bybit.us`, `bybit.eu` |
| `ADMIN_USER_IDS` | | | Telegram user IDs with admin access, comma-separated |
| `ALERT_HISTORY_DAYS` | | `7` | Days of alert history kept in MongoDB (minimum 1) |
| `DEX_ENABLED` | | `true` | Solana DEX tracking (only runs when `BIRDEYE_API_KEY` is set) |
| `BIRDEYE_API_KEY` | | | Birdeye API key for DEX alerts |
| `DEX_BIG_BUY_USD` | | `5000` | Minimum buy size for a DEX "big buy" alert |
| `DEX_WHALE_BUY_USD` | | `25000` | Minimum buy size for a 🐋 whale alert |
| `ENVIRONMENT` | | `development` | `development` or `production` |

To find your Telegram user ID for `ADMIN_USER_IDS`, message [@userinfobot](https://t.me/userinfobot).

### 6. Run

```bash
python main.py
```

You should see something like:
```
✓ Connected to BINANCE
✓ Connected to BYBIT
✓ Connected to MEXC
✓ Connected to BITGET
✓ Connected to GATEIO
🚀 Starting Top Gainers Bot...
✓ Registered command handlers
✓ Connected to MongoDB
🌐 DEX Tracking: DISABLED - set BIRDEYE_API_KEY to enable (free key at https://birdeye.so/)
✅ Bot is running!
📊 Monitoring 5 CEX exchanges
⏱️  Check interval: 60s
📈 Spike threshold: 30.0%-70.0%
🔍 Spike tracker started
```

### 7. Tests

The tests use fakes, so they need no Telegram, MongoDB or network access:

```bash
pip install pytest mongomock-motor
python -m pytest
```

## Usage

### Commands

| Command | Description |
|---|---|
| `/start` | Register and open the main menu |
| `/gainers` | Top gainers (pick an exchange, then 5/10/20) |
| `/losers` | Top losers |
| `/alerts` | Turn alerts on or off, choose alert types and exchanges |
| `/watchlist` | Show your watchlist |
| `/watchlist add BTC` | Add a coin (`BTC` and `BTCUSDT` both work) |
| `/watchlist remove BTC` | Remove a coin |
| `/watchlist clear` | Remove all coins |
| `/help` | Help |

### Admin Commands

Only users listed in `ADMIN_USER_IDS` can use these.

| Command | Description |
|---|---|
| `/broadcast <message>` | Send an announcement to all users (multi-line text is kept) |
| `/stats_admin` | Users, alerts, watchlists and monitored exchanges |
| `/ban <user_id> [reason]` | Block a user from the bot and its alerts |
| `/unban <user_id>` | Unblock a user |

## MongoDB Collections

| Collection | Contents | Growth |
|---|---|---|
| `users` | Telegram ID, name, `alerts_enabled`, timestamps | One per user |
| `user_preferences` | `alert_exchanges`, `alert_types` (on/off per alert type) | One per user |
| `watchlists` | `user_id`, `symbols` | One per user |
| `banned_users` | `user_id`, `banned_by`, `reason`, `banned_at` | One per ban |
| `alert_history` | `symbol`, `exchange`, `alert_type`, `percent_gain`, `alerted_at` | Deleted automatically after `ALERT_HISTORY_DAYS` |
| `counters` | All-time number of alerts sent (for `/stats_admin`) | One document |

Each alert is stored once, not once per user. Alert history is only needed so cooldowns survive a restart; Telegram's chat history can't be used for that because bots can't read the messages they've sent.

## Customization

### Faster Alerts

```env
SPIKE_CHECK_INTERVAL=30
```

Each scan downloads the full ticker list from every exchange in `EXCHANGES`, so halving the interval doubles the API calls.

### Alert Thresholds

The daily band is set in `.env` (`MIN_SPIKE_THRESHOLD`, `MAX_SPIKE_THRESHOLD`). The 5-minute pump/dump threshold, pump score weights and cooldowns are constants at the top of `monitoring/tracker.py`.

### Add More Exchanges

CCXT supports 100+ exchanges:

1. Check [CCXT Supported Exchanges](https://github.com/ccxt/ccxt#supported-cryptocurrency-exchange-markets)
2. Add it to `SUPPORTED_EXCHANGES` and `EXCHANGE_CONFIGS` in `exchanges/client.py`, and a trading link in `_generate_trade_link`
3. Add it to `EXCHANGES` in `.env`, and to the keyboards in `bot/keyboards.py` and `ALL_EXCHANGES` in `database/client.py`

## Deployment

The bot uses long polling, so it runs as a **background worker** (no web port needed). Run only one instance per bot token.

### Railway

```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

Set the environment variables in the Railway dashboard.

### Render

1. Connect the GitHub repo and create a **Background Worker**
2. Build command: `pip install -r requirements.txt`
3. Start command: `python main.py`
4. Set the environment variables in the dashboard

### VPS (DigitalOcean, AWS, etc.)

```bash
git clone <your_repo_url>
cd top-gainers-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env
```

Create `/etc/systemd/system/topgainers.service`:
```ini
[Unit]
Description=Top Gainers Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/top-gainers-bot
ExecStart=/path/to/top-gainers-bot/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now topgainers
journalctl -u topgainers -f   # follow the logs
```

## Troubleshooting

### Bot Not Responding
- Check `TELEGRAM_BOT_TOKEN` in `.env`
- Make sure only one copy of the bot is running (two instances with one token conflict)
- Check the logs for `⚠️ Error handling update`

### MongoDB Connection Failed
- Check `MONGODB_URL`, and URL-encode special characters in the password
- Make sure the Atlas cluster is running and your server's IP is allowed under Network Access
- Test the connection: `mongosh "<connection_string>"`

### No Alerts
- Alerts are off by default: enable them with `/alerts`
- Check "🎚️ Alert Types" and "🛠️ Filter Exchanges" in `/alerts`
- Pump and dump alerts need 5 minutes of price history, so none fire in the first 5 minutes after a start
- Check the logs for `✓ Connected to ...` and `Error fetching from ...`

### No DEX Alerts
- Set `BIRDEYE_API_KEY`; without it the DEX tracker doesn't start
- Make sure "🌐 DEX Alerts" is on under `/alerts` → "Alert Types"

### Exchange API Errors
- Some exchanges block certain regions (Bybit: try `BYBIT_HOSTNAME`; Binance blocks some cloud regions)
- Check the exchange's status page
- Temporarily remove the failing exchange from `EXCHANGES`

## Roadmap

See [IMPROVEMENTS.md](IMPROVEMENTS.md).

## Contributing

Issues and enhancement requests are welcome.

## License

MIT License

---

**Happy Trading! 🚀📈**

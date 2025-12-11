# Top Gainers Telegram Bot

A powerful Telegram bot that tracks top-performing futures/derivatives across major crypto exchanges and sends real-time spike alerts.

## Features

- 📊 **Top Gainers Tracking**: View top 5/10/20 gainers across Binance, Bybit, MEXC, Bitget, and Gate.io
- 🚨 **Spike Alerts**: Real-time notifications for 30-70% sudden gains
- 🎯 **Smart Filtering**: Filter by exchange or view all exchanges combined
- 💾 **Persistent Storage**: User preferences saved with MongoDB
- ⚡ **Real-time Monitoring**: Background task continuously monitors all exchanges
- 📜 **Chat History**: Keeps all viewed gainers in chat history for easy reference

## Tech Stack

- **Python 3.11+**
- **python-telegram-bot 21.0** - Telegram Bot API
- **CCXT 4.2.25** - Unified exchange API
- **Motor 3.3.2** - Async MongoDB driver
- **MongoDB** - NoSQL database
- **asyncio** - Async operations

## Project Structure

```
top-gainers-bot/
├── bot/
│   ├── __init__.py
│   ├── handlers.py       # Command & callback handlers
│   ├── keyboards.py      # Inline keyboards
│   └── messages.py       # Message templates
├── database/
│   ├── __init__.py
│   └── client.py         # MongoDB client wrapper
├── exchanges/
│   ├── __init__.py
│   └── client.py         # Exchange API wrapper (CCXT)
├── monitoring/
│   ├── __init__.py
│   └── tracker.py        # Spike detection & alerts
├── config.py             # Configuration management
├── main.py               # Application entry point
├── requirements.txt      # All dependencies
├── .env.example          # Environment template
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

## Setup Instructions

### 1. Prerequisites

- Python 3.11 or higher
- MongoDB Atlas account (free tier M0 cluster)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 2. Clone & Install

```bash
# Navigate to project
cd top-gainers-bot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. MongoDB Setup

#### Create MongoDB Atlas Database

1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create a free account
3. Create a new **M0 Free Cluster**
4. Under "Security" → "Database Access" → Create database user with username & password
5. Under "Security" → "Network Access" → Add your IP (or 0.0.0.0/0 for testing)
6. Click "Connect" and copy the connection string
7. Replace `<username>` and `<password>` with your credentials

The connection string should look like:
```
mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

**Important:** If your password contains special characters (like `@`, `#`, etc.), URL-encode them:
- `@` → `%40`
- `#` → `%23`
- `:` → `%3A`

### 4. Environment Configuration

Create `.env` file from template:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# MongoDB Connection String
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority

# Monitoring Settings
SPIKE_CHECK_INTERVAL=60          # Check every 60 seconds
MIN_SPIKE_THRESHOLD=30           # Alert on gains 30%+
MAX_SPIKE_THRESHOLD=70           # Alert on gains up to 70%

# Exchanges to Monitor
EXCHANGES=binance,bybit,mexc,bitget,gateio

# Environment
ENVIRONMENT=development          # or 'production'
```

### 5. Get Telegram Bot Token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Follow the instructions to create your bot
4. Copy the token and add it to `.env`

### 6. Run the Bot

```bash
# Make sure venv is activated
python main.py
```

You should see:
```
✓ Connected to BINANCE
✓ Connected to BYBIT
✓ Connected to MEXC
✓ Connected to BITGET
✓ Connected to GATEIO
🚀 Starting Top Gainers Bot...
✓ Registered command handlers
✓ Connected to MongoDB
✅ Bot is running!
📊 Monitoring 5 exchanges
⏱️  Check interval: 60s
📈 Spike threshold: 30.0%-70.0%
🔍 Spike tracker started
```

## Usage

### User Commands

- `/start` - Initialize bot and see welcome message
- `/gainers` - View top gainers (select exchange and count)
- `/alerts` - Enable/disable spike alerts
- `/help` - Show help information

### How It Works

#### 1. Manual Queries (Top Gainers)
- User sends `/gainers`
- Selects exchange (Binance, Bybit, MEXC, Bitget, Gate.io, or All)
- Selects top count (5, 10, or 20)
- Bot fetches and displays results
- Results stay in chat history for reference

#### 2. Automatic Alerts (Spike Detection)
- Background task monitors all exchanges every 60 seconds
- Detects sudden spikes between 30-70% gain
- Sends notifications to users with alerts enabled
- Prevents duplicate alerts within 1 hour

## MongoDB Schema

### Users Collection
```javascript
{
  _id: ObjectId,
  id: Number,           // Telegram user ID
  username: String,
  first_name: String,
  alerts_enabled: Boolean,
  created_at: Date,
  last_active: Date
}
```

### User Preferences Collection
```javascript
{
  _id: ObjectId,
  user_id: Number,
  preferred_exchanges: [String],
  default_top_count: Number,
  min_alert_threshold: Number,
  max_alert_threshold: Number
}
```

### Alert History Collection
```javascript
{
  _id: ObjectId,
  symbol: String,
  exchange: String,
  percent_gain: Number,
  alerted_at: Date
}
```

### Price Snapshots Collection
```javascript
{
  _id: ObjectId,
  symbol: String,
  exchange: String,
  price: Number,
  volume_24h: Number,
  percent_change_24h: Number,
  timestamp: Date
}
```

## Customization

### Change Monitoring Interval

Edit `.env`:
```env
SPIKE_CHECK_INTERVAL=30  # Check every 30 seconds instead of 60
```

### Adjust Spike Thresholds

Edit `.env`:
```env
MIN_SPIKE_THRESHOLD=20   # Lower bound (20% minimum)
MAX_SPIKE_THRESHOLD=100  # Upper bound (up to 100%)
```

### Add More Exchanges

CCXT supports 100+ exchanges. To add more:

1. Check [CCXT Supported Exchanges](https://github.com/ccxt/ccxt#supported-cryptocurrency-exchange-markets)
2. Add exchange to `exchanges/client.py` in `SUPPORTED_EXCHANGES` dict
3. Update `.env` EXCHANGES list

Example:
```python
# In exchanges/client.py
SUPPORTED_EXCHANGES = {
    'binance': ccxt.binance,
    'bybit': ccxt.bybit,
    'kucoin': ccxt.kucoin,  # Add new exchange
    ...
}
```

## Deployment

### Option 1: Railway

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

### Option 2: Render

1. Connect GitHub repo to Render
2. Set environment variables in Render dashboard
3. Deploy as Background Worker
4. Set start command: `python main.py`

### Option 3: Heroku

```bash
# Install Heroku CLI
# Login and deploy
heroku login
heroku create your-bot-name
git push heroku main
```

### Option 4: VPS (DigitalOcean, AWS, etc.)

```bash
# SSH into your VPS
ssh user@your_vps_ip

# Clone repo
git clone <your_repo_url>
cd top-gainers-bot

# Create and activate venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
nano .env
# Paste your environment variables

# Run with systemd (for persistent execution)
sudo nano /etc/systemd/system/topgainers.service
```

Add this to the service file:
```ini
[Unit]
Description=Top Gainers Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/top-gainers-bot
ExecStart=/path/to/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable topgainers
sudo systemctl start topgainers
```

## Troubleshooting

### Bot Not Responding

- Check `TELEGRAM_BOT_TOKEN` is correct in `.env`
- Ensure bot is running: `python main.py`
- Check logs for error messages
- Verify bot is active in Telegram (@BotFather → /mybots)

### MongoDB Connection Failed

- Verify `MONGODB_URL` in `.env` is correct
- Check MongoDB Atlas cluster is running (green status)
- Verify IP whitelist includes your computer's IP
- Test connection: `mongosh <connection_string>`
- Check username/password are URL-encoded if they contain special characters

### No Spike Alerts

- Verify `SPIKE_CHECK_INTERVAL` is set and > 0
- Check exchange connections in logs (should show ✓ for all)
- Ensure users have alerts enabled (use `/alerts` command)
- Monitor logs for "Spike tracker started"

### Exchange API Errors

- CCXT has rate limits - bot implements retries
- Check if exchange is down: visit exchange status page
- Verify internet connection
- Try reducing number of exchanges temporarily

### High Memory Usage

- Reduce `SPIKE_CHECK_INTERVAL` slightly
- Limit number of exchanges monitored
- Check for memory leaks in logs

## Contributing

Feel free to submit issues and enhancement requests!

## License

MIT License

## Support

Questions? Issues? 
- Open a GitHub issue
- Contact [@your_telegram_username]

---

**Happy Trading! 🚀📈**
EXCHANGES=binance,bybit,mexc,bitget
```

### 5. Get Telegram Bot Token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Follow instructions to create bot
4. Copy token and add to `.env`

### 6. Run the Bot

```bash
python main.py
```

You should see:
```
🚀 Starting Top Gainers Bot...
✓ Connected to database
✓ Connected to BINANCE
✓ Connected to BYBIT
✓ Connected to MEXC
✓ Connected to BITGET
✓ Registered command handlers
✓ Bot setup complete
✅ Bot is running!
```

## Usage

### User Commands

- `/start` - Initialize bot and see welcome message
- `/gainers` - View top gainers (interactive filters)
- `/alerts` - Enable/disable spike alerts
- `/help` - Show help information

### How It Works

1. **Manual Queries**: 
   - User sends `/gainers`
   - Selects exchange (or "All")
   - Selects top count (5/10/20)
   - Bot fetches and displays results

2. **Automatic Alerts**:
   - Background task monitors all exchanges every 60s
   - Detects spikes between 30-70%
   - Sends push notifications to users with alerts enabled
   - Prevents duplicate alerts within 1 hour

## Database Schema

### Users Table
Stores user info and alert preferences

### User Preferences Table
Custom settings per user (exchanges, thresholds)

### Price Snapshots Table
Historical price data for trend analysis

### Alert History Table
Tracks sent alerts to prevent duplicates

## Customization

### Change Monitoring Interval

Edit `.env`:
```env
SPIKE_CHECK_INTERVAL=30  # Check every 30 seconds
```

### Adjust Spike Thresholds

Edit `.env`:
```env
MIN_SPIKE_THRESHOLD=20  # Lower bound
MAX_SPIKE_THRESHOLD=100 # Upper bound
```

### Add More Exchanges

CCXT supports 100+ exchanges. To add more:

1. Check [CCXT Supported Exchanges](https://github.com/ccxt/ccxt#supported-cryptocurrency-exchange-markets)
2. Add to `exchanges/client.py` in `SUPPORTED_EXCHANGES`
3. Update `.env` EXCHANGES list

## Deployment

### Option 1: Railway

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and init
railway login
railway init
railway up
```

### Option 2: Render

1. Connect GitHub repo
2. Set environment variables
3. Deploy as Background Worker

### Option 3: VPS

```bash
# Install supervisor
sudo apt install supervisor

# Create supervisor config
sudo nano /etc/supervisor/conf.d/topgainers.conf

# Add:
[program:topgainers]
directory=/path/to/bot
command=/path/to/venv/bin/python main.py
autostart=true
autorestart=true
```

## Troubleshooting

### Bot Not Responding
- Check `TELEGRAM_BOT_TOKEN` is correct
- Ensure bot is running (`python main.py`)
- Check logs for errors

### Database Connection Failed
- Verify `DATABASE_URL` in `.env`
- Run `prisma db push` again
- Check Neon dashboard for connection issues

### No Spike Alerts
- Verify `SPIKE_CHECK_INTERVAL` is set
- Check exchange connections in logs
- Ensure users have alerts enabled

### Exchange API Errors
- CCXT rate limits may apply
- Check exchange status pages
- Wait and retry

## Contributing

Feel free to submit issues and enhancement requests!

## License

MIT License

## Support

Questions? Issues? Open a GitHub issue or contact [@yourusername]

---

**Happy Trading! 🚀📈**
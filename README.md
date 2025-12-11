# Top Gainers Telegram Bot

A powerful Telegram bot that tracks top-performing futures/derivatives across major crypto exchanges and sends real-time spike alerts.

## Features

- 📊 **Top Gainers Tracking**: View top 5/10/20 gainers across Binance, Bybit, MEXC, and Bitget
- 🚨 **Spike Alerts**: Real-time notifications for 30-70% sudden gains
- 🎯 **Smart Filtering**: Filter by exchange or view all exchanges combined
- 💾 **Persistent Storage**: User preferences saved with Neon PostgreSQL + Prisma
- ⚡ **Real-time Monitoring**: Background task continuously monitors all exchanges

## Tech Stack

- **Python 3.11+**
- **python-telegram-bot** - Telegram Bot API
- **CCXT** - Unified exchange API
- **Prisma** - Modern ORM
- **Neon PostgreSQL** - Serverless database
- **asyncio** - Async operations

## Project Structure

```
top-gainers-bot/
├── bot/
│   ├── handlers.py       # Command & callback handlers
│   ├── keyboards.py      # Inline keyboards
│   └── messages.py       # Message templates
├── exchanges/
│   └── client.py         # Exchange API wrapper
├── monitoring/
│   └── tracker.py        # Spike detection & alerts
├── database/
│   └── (Prisma manages this)
├── prisma/
│   └── schema.prisma     # Database schema
├── config.py             # Configuration
├── main.py               # Entry point
├── requirements.txt      # Dependencies
└── .env                  # Environment variables
```

## Setup Instructions

### 1. Prerequisites

- Python 3.11 or higher
- Neon PostgreSQL account (free tier works)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 2. Clone & Install

```bash
# Create project directory
mkdir top-gainers-bot
cd top-gainers-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Setup

#### Create Neon Database

1. Go to [neon.tech](https://neon.tech) and create account
2. Create a new project
3. Copy your connection string (looks like: `postgresql://user:pass@ep-xxx.neon.tech/dbname`)

#### Generate Prisma Client

```bash
# Generate Prisma client
prisma generate

# Push schema to database
prisma db push
```

### 4. Environment Configuration

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
DATABASE_URL=postgresql://user:password@ep-xxx.neon.tech/dbname?sslmode=require
SPIKE_CHECK_INTERVAL=60
MIN_SPIKE_THRESHOLD=30
MAX_SPIKE_THRESHOLD=70
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
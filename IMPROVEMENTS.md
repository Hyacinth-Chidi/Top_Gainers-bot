# 🚀 Top Gainers Bot - Improvement Roadmap

A comprehensive list of suggested improvements and enhancements for the bot.
Check items as they are implemented.

---

## 🔥 High Priority - Core Features

### 1. [x] Add Loser Alerts (Dump Detection) ✅ COMPLETED

Currently, only gainers trigger alerts. Add detection for sudden dumps (e.g., -5% in 5 minutes) for short traders.

**Files modified:**

- `monitoring/tracker.py` - Added dump detection logic (5-min and daily)
- `bot/messages.py` - Added dump alert message templates

---

### 2. [ ] Customizable Alert Thresholds Per User

Let users set their own thresholds instead of using global config:

- Min/Max spike percentage
- Volatility window (1m, 5m, 15m)
- Volume filter (only alert on high-volume coins)

**Files to modify:**

- `database/client.py` - Add threshold fields to user_preferences
- `bot/handlers.py` - Add `/settings` command
- `bot/keyboards.py` - Add settings keyboard
- `monitoring/tracker.py` - Use per-user thresholds

---

### 3. [x] Watchlist Feature ✅ COMPLETED

Allow users to track specific coins and get alerts only for those:

```
/watchlist add BTCUSDT
/watchlist remove ETHUSDT
/watchlist show
```

**Files modified:**

- `database/client.py` - Added watchlist collection and CRUD methods
- `bot/handlers.py` - Added watchlist command handler
- `bot/keyboards.py` - Added watchlist menu keyboard
- `bot/messages.py` - Added watchlist message templates
- `main.py` - Registered /watchlist command

---

### 4. [ ] Market Stats Command

Add `/stats` to show market overview:

- Total market sentiment (% gainers vs losers)
- Most volatile coins today
- Highest volume coins

**Files to modify:**

- `bot/handlers.py` - Add stats_command
- `bot/messages.py` - Add stats message template
- `exchanges/client.py` - Add get_market_stats method

---

### 5. [ ] Scheduled Reports

Daily/weekly summary sent automatically:

- Top 10 gainers/losers of the day
- Best performers of the week
- User's watchlist performance

**Files to modify:**

- `monitoring/tracker.py` or new `monitoring/scheduler.py`
- `database/client.py` - Store daily snapshots
- `bot/messages.py` - Add report templates

---

## ⚡ Medium Priority - Performance & Reliability

### 6. [ ] Caching Layer (Redis)

Add Redis to cache exchange data and reduce API calls:

```python
# Cache tickers for 30 seconds
cached_tickers = await redis.get(f"tickers:{exchange}")
if not cached_tickers:
    tickers = await fetch_from_exchange()
    await redis.set(f"tickers:{exchange}", tickers, ex=30)
```

**New files:**

- `cache/redis_client.py`

**Dependencies:**

- `aioredis` or `redis[async]`

---

### 7. [ ] Retry Logic with Exponential Backoff

Improve resilience for exchange API failures:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
async def fetch_tickers(self, exchange):
    ...
```

**Files to modify:**

- `exchanges/client.py`

**Dependencies:**

- `tenacity`

---

### 8. [ ] Connection Pooling for MongoDB

Add connection pool settings for better performance:

```python
self.client = AsyncIOMotorClient(
    config.MONGODB_URL,
    maxPoolSize=50,
    minPoolSize=10
)
```

**Files to modify:**

- `database/client.py`

---

### 9. [ ] Health Check Endpoint

Add a simple HTTP endpoint for monitoring (useful for deployment):

```python
from aiohttp import web

async def health_check(request):
    return web.json_response({"status": "ok", "uptime": ...})
```

**New files:**

- `api/health.py`

**Dependencies:**

- `aiohttp`

---

## 🎨 User Experience Enhancements

### 10. [ ] Pagination for Results

When showing 20+ coins, add pagination buttons:

```
[← Previous] [Page 1/3] [Next →]
```

**Files to modify:**

- `bot/handlers.py` - Handle pagination callbacks
- `bot/keyboards.py` - Add pagination keyboard
- `bot/messages.py` - Format paginated results

---

### 11. [ ] Refresh Button

Add "🔄 Refresh" button to update results without starting over:

```python
InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh:{exchange}:{count}")
```

**Files to modify:**

- `bot/keyboards.py` - Add refresh button to results
- `bot/handlers.py` - Handle refresh callback

---

### 12. [ ] Mini Charts (Sparklines)

Use text-based sparklines to show price trend:

```
BTCUSDT ▁▂▃▅▆▇ +5.2%
```

**Files to modify:**

- `bot/messages.py` - Add sparkline generator
- `database/client.py` - Ensure price history is available

---

### 13. [ ] Favorite Exchanges

Remember user's last selected exchange and pre-select it next time.

**Files to modify:**

- `database/client.py` - Add last_exchange to preferences
- `bot/handlers.py` - Load user's preferred exchange

---

### 14. [ ] Alert Sound/Priority Settings

Let users choose alert urgency (silent, normal, urgent) which affects Telegram notification settings.

**Files to modify:**

- `database/client.py` - Add notification_priority to preferences
- `bot/handlers.py` - Add priority selection
- `monitoring/tracker.py` - Use disable_notification parameter

---

## 📊 Analytics & Insights

### 15. [ ] Alert Performance Tracking

Track how coins perform after alerts:

- "This coin pumped +15% after our alert 2 hours ago"
- Weekly accuracy report

**Files to modify:**

- `database/client.py` - Add performance tracking collection
- `monitoring/tracker.py` - Calculate post-alert performance
- `bot/messages.py` - Add performance report template

---

### 16. [ ] User Activity Analytics

Track which features are used most:

- Most requested exchanges
- Average top count selected
- Peak usage hours

**New files:**

- `analytics/tracker.py`

**Files to modify:**

- `bot/handlers.py` - Log user actions

---

### 17. [ ] Coin History Command

```
/history BTCUSDT
→ Shows last 24h price action, volume, and any alerts sent
```

**Files to modify:**

- `bot/handlers.py` - Add history_command
- `bot/messages.py` - Add history message template
- `database/client.py` - Query price_snapshots

---

## 🔒 Security & Stability

### 18. [ ] Rate Limiting for Users

Prevent abuse by limiting requests per user (max 10 commands per minute):

**Files to modify:**

- `bot/handlers.py` - Add rate limit decorator
- `database/client.py` - Track request counts (or use in-memory)

---

### 19. [x] Admin Commands ✅ COMPLETED

Add admin-only commands:

```
/broadcast <message>  - Send message to all users
/stats_admin          - Show bot statistics
/ban <user_id>        - Block abusive users
/unban <user_id>      - Unblock a user
```

**Files modified:**

- `config.py` - Added ADMIN_USER_IDS from environment variable
- `database/client.py` - Added banned_users collection with ban/unban/is_banned/get_bot_stats methods
- `bot/handlers.py` - Added broadcast_command, stats_admin_command, ban_command, unban_command
- `main.py` - Registered admin commands

---

### 20. [ ] Graceful Error Handling

Show user-friendly errors instead of silently failing:

```python
except ExchangeError:
    await update.message.reply_text("⚠️ Exchange temporarily unavailable. Try again in a minute.")
```

**Files to modify:**

- `bot/handlers.py` - Wrap handlers in try/except
- `bot/messages.py` - Add error message templates

---

### 21. [ ] Database Backup Strategy

Implement automated MongoDB backups.

**Options:**

- MongoDB Atlas scheduled backups (recommended)
- Custom backup script using `mongodump`

---

## 🌐 New Exchange Support

### 22. [ ] Add More Exchanges

Easy to add with CCXT:

- **OKX** (okx)
- **KuCoin** (kucoin)
- **Huobi** (huobi)
- **Kraken** (kraken)

**Files to modify:**

- `exchanges/client.py` - Add to SUPPORTED_EXCHANGES and EXCHANGE_CONFIGS
- `bot/keyboards.py` - Add new exchange buttons

---

## 📱 Modern Bot Features

### 23. [ ] Inline Mode

Let users query directly in any chat:

```
@YourBot BTCUSDT
→ Shows price, 24h change inline
```

**Files to modify:**

- `main.py` - Register InlineQueryHandler
- `bot/handlers.py` - Add inline_query handler

---

### 24. [ ] Web App (Mini App)

Build a Telegram Web App for better UX:

- Interactive charts
- Real-time price updates
- Advanced filtering

**New directory:**

- `webapp/` - HTML/JS/CSS for the mini app

---

### 25. [ ] Multi-Language Support

Add i18n for Russian, Chinese, Spanish markets:

```python
messages = load_messages(user.language or 'en')
```

**New directory:**

- `locales/` - Language files (en.json, ru.json, etc.)

**Files to modify:**

- `bot/messages.py` - Load from locale files
- `database/client.py` - Store user language preference

---

## 🛠️ Code Quality

### 26. [ ] Logging System

Replace `print()` with proper logging:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Connected to %s", exchange_name)
```

**Files to modify:**

- All files - Replace print statements
- `main.py` - Configure logging

---

### 27. [ ] Type Hints Throughout

Add consistent type hints for better IDE support and documentation.

**Files to modify:**

- All Python files

---

### 28. [ ] Unit Tests

Add pytest tests for:

- Exchange client methods
- Message formatting
- Alert logic

**New directory:**

- `tests/`

**Dependencies:**

- `pytest`
- `pytest-asyncio`

---

### 29. [ ] Docker Deployment

Add containerization for easy deployment.

**New files:**

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

---

## 📋 Implementation Priority Matrix

| #   | Enhancement       | Effort    | Impact    | Priority |
| --- | ----------------- | --------- | --------- | -------- |
| 11  | Refresh Button    | 🟢 Low    | 🔥 High   | ⭐⭐⭐   |
| 26  | Logging System    | 🟢 Low    | 🟡 Medium | ⭐⭐⭐   |
| 20  | Error Handling    | 🟢 Low    | 🔥 High   | ⭐⭐⭐   |
| 1   | Loser Alerts      | 🟡 Medium | 🔥 High   | ⭐⭐⭐   |
| 3   | Watchlist         | 🟡 Medium | 🔥 High   | ⭐⭐⭐   |
| 4   | Market Stats      | 🟡 Medium | 🔥 High   | ⭐⭐     |
| 10  | Pagination        | 🟡 Medium | 🟡 Medium | ⭐⭐     |
| 7   | Retry Logic       | 🟢 Low    | 🟡 Medium | ⭐⭐     |
| 19  | Admin Commands    | 🟡 Medium | 🟡 Medium | ⭐⭐     |
| 6   | Redis Caching     | 🟡 Medium | 🔥 High   | ⭐⭐     |
| 2   | Custom Thresholds | 🔴 High   | 🔥 High   | ⭐       |
| 5   | Scheduled Reports | 🔴 High   | 🟡 Medium | ⭐       |
| 24  | Web App           | 🔴 High   | 🔥 High   | ⭐       |

---

## ✅ Completed Improvements

_Move items here once implemented:_

- **#1 - Dump Detection** (2026-01-02): Added detection for sudden dumps (-5% in 5 mins) and daily losers (-30% to -70%). Users now receive alerts for both pump and dump events.

- **#3 - Watchlist Feature** (2026-01-02): Added `/watchlist` command with add/remove/clear/show operations. Users can now track specific coins. Includes database collection, command handlers, and UI keyboards.

- **#19 - Admin Commands** (2026-01-02): Added `/broadcast`, `/stats_admin`, `/ban`, `/unban` commands. Admins configured via ADMIN_USER_IDS env variable.

---

## 📝 Notes

- Start with "Quick Wins" (low effort, high impact)
- Test each feature thoroughly before moving to the next
- Keep the bot running during development using feature flags if needed

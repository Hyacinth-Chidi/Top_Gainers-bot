# Deploying Top Gainers Bot to Render

## Prerequisites
- Render account (free at https://render.com)
- GitHub account with your bot code pushed
- Telegram Bot Token (you already have this)
- MongoDB Atlas connection string

## Step-by-Step Deployment

### Step 1: Push Latest Code to GitHub
Make sure all your code is committed and pushed:
```bash
git add -A
git commit -m "Prepare for Render deployment"
git push origin main
```

### Step 2: Create a Render Account
1. Go to https://render.com
2. Sign up with GitHub (recommended for easier integration)
3. Authorize Render to access your GitHub repositories

### Step 3: Create a New Web Service
1. Dashboard → New + → Web Service
2. Connect your GitHub repository `Top_Gainers-bot`
3. Fill in the details:
   - **Name**: `top-gainers-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: Free (sufficient for monitoring bot)

### Step 4: Set Environment Variables
Before deploying, add these environment variables in Render:

1. In the Web Service dashboard, go to **Environment**
2. Add the following variables:

| Key | Value | Type |
|-----|-------|------|
| `TELEGRAM_BOT_TOKEN` | Your bot token | **Secret** ⚠️ |
| `MONGODB_URL` | Your MongoDB Atlas connection string | **Secret** ⚠️ |
| `BYBIT_HOSTNAME` | `bybit.com` | Regular |
| `SPIKE_CHECK_INTERVAL` | `60` | Regular |
| `MIN_SPIKE_THRESHOLD` | `30` | Regular |
| `MAX_SPIKE_THRESHOLD` | `70` | Regular |
| `EXCHANGES` | `binance,bybit,mexc,bitget,gateio` | Regular |
| `ENVIRONMENT` | `production` | Regular |

**⚠️ IMPORTANT**: Mark `TELEGRAM_BOT_TOKEN` and `MONGODB_URL` as **Secret** so they're encrypted.
- In the Render dashboard, you'll see a toggle for each variable - toggle it to "Secret" for sensitive values
- Do NOT add secrets to `render.yaml` (they must be set manually in the dashboard)

### Step 5: Deploy
1. Click the **Deploy** button
2. Watch the build logs:
   - Dependencies installation
   - Bot initialization
   - MongoDB connection verification
3. Deployment complete when status shows **Live** (green)

### Step 6: Monitor Deployment
- **Logs**: View real-time logs in the Render dashboard
- **Metrics**: Monitor CPU and memory usage
- **Health**: Render will restart the service if it crashes

## Common Issues & Fixes

### Issue: "ModuleNotFoundError: No module named 'ccxt'"
**Solution**: requirements.txt is missing. Make sure `pip install -r requirements.txt` is in build command.

### Issue: "Cannot connect to MongoDB"
**Solution**: 
- Verify `MONGODB_URL` is correct and has `%40` for @ symbol
- Check MongoDB Atlas allows IP `0.0.0.0/0` (all IPs)
- Whitelist Render's IP: In MongoDB Atlas → Network Access → Add 0.0.0.0/0

### Issue: "Telegram API connection failed"
**Solution**: 
- Verify `TELEGRAM_BOT_TOKEN` is exactly correct
- Check Render can reach telegram.org (usually allowed)

### Issue: Bot keeps restarting
**Solution**:
- Check logs for errors
- Verify all environment variables are set
- Ensure bot doesn't have infinite loops or memory leaks

## Keeping Your Bot Running 24/7

Render's **Free tier**:
- ✅ Keeps service running 24/7
- ✅ Auto-restarts if it crashes
- ⚠️ No SLA guarantee (community tier)
- ✅ Perfect for development/testing

**Paid tier** (if you need reliability):
- $7/month for guaranteed uptime SLA
- Priority support

## Updating Your Bot on Render

To deploy updates:

### Method 1: Auto-deploy on Git push
1. Render → Settings → Auto-Deploy: `Yes`
2. Then every `git push origin main` auto-deploys

### Method 2: Manual Deploy
1. Render Dashboard
2. Click your service
3. Click **Redeploy** button

```bash
# After making changes locally:
git add -A
git commit -m "Update: description of changes"
git push origin main
# Render auto-deploys (if enabled)
```

## Verifying Deployment

Once deployed, verify these:

✅ Bot is responding to `/start` command on Telegram
✅ Logs show "Bot is running!" message
✅ Spike alerts are being sent
✅ No error messages in logs

## Logs Command

View logs in Render dashboard or use tail command:
```
# In Render dashboard → Logs tab
# Follow logs in real-time
```

## Troubleshooting Logs

Look for these indicators:
- ✓ `✓ Connected to BINANCE` - Exchange connection works
- ✓ `✓ Connected to MongoDB` - Database connection works
- ✓ `✅ Bot is running!` - Bot successfully started
- ✗ `Error fetching data from X` - Exchange API issue (normal, retries automatically)
- ✗ `Cannot connect to MongoDB` - Check connection string and IP whitelist

## Next Steps

1. **Monitor logs** for first 24 hours
2. **Test spike alerts** by manually checking when currencies spike
3. **Set up monitoring** - Use Render's built-in alerts for service restarts
4. **Upgrade if needed** - Move to paid tier if you need guaranteed uptime

## Cost Estimate

- **Free tier**: $0/month ✅
  - Your bot will run on shared infrastructure
  - Suitable for most use cases

- **Pro tier**: $7/month
  - Dedicated instance
  - SLA guarantee

## Support

If you have issues:
1. Check Render's documentation: https://render.com/docs
2. View service logs in dashboard
3. Check MongoDB Atlas connectivity
4. Verify Telegram Bot Token

---

**Questions?** Let me know and I'll help debug!

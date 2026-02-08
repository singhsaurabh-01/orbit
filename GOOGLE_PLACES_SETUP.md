# Google Places API Setup Guide

## Step 1: Create Google Cloud Project

1. Go to: **https://console.cloud.google.com/**
2. Click **"Select a project"** → **"New Project"**
3. Name it: **"Orbit"** (or any name)
4. Click **"Create"**
5. Wait for project creation (~30 seconds)

## Step 2: Enable Places API

1. In the Google Cloud Console, go to: **APIs & Services** → **Library**
   - Or direct link: https://console.cloud.google.com/apis/library
2. Search for: **"Places API"**
3. Click on **"Places API (New)"**
4. Click **"Enable"**

## Step 3: Create API Key

1. Go to: **APIs & Services** → **Credentials**
   - Or direct link: https://console.cloud.google.com/apis/credentials
2. Click **"+ CREATE CREDENTIALS"** → **"API key"**
3. Copy the API key (starts with `AIza...`)
4. Click **"Close"**

## Step 4: Restrict API Key (IMPORTANT - Save Money!)

1. Click on the API key you just created
2. Under **"Application restrictions"**:
   - Select **"IP addresses"**
   - Add your server IP (or leave unrestricted for local testing)
3. Under **"API restrictions"**:
   - Select **"Restrict key"**
   - Check **"Places API"** only
4. Click **"Save"**

## Step 5: Set Up Billing & Budget Alerts

### Enable Billing (Required)
1. Go to: **Billing** → **Account Management**
2. Link a credit/debit card
3. Note: Google gives **$200 free credit per month** for new users

### Set Budget Alerts (Highly Recommended)
1. Go to: **Billing** → **Budgets & alerts**
2. Click **"CREATE BUDGET"**
3. Set amount: **$20** (or your limit)
4. Set alerts at: **50%, 90%, 100%**
5. Add your email for notifications
6. Click **"Finish"**

## Step 6: Add API Key to Orbit

1. Open your `.env` file in the Orbit project
2. Add the line:
   ```env
   GOOGLE_PLACES_API_KEY=AIza...your_key_here
   ```
3. Save the file

## Step 7: Test It!

Run this to test if it works:

```bash
uv run python -c "
from orbit.services.google_places import search_place_with_google
result = search_place_with_google('Target', 41.8781, -87.6298, 25)
print(f'✅ Google Places works!' if result else '❌ API key issue')
print(f'Found: {result.name}' if result else '')
"
```

## Cost Breakdown

### Pricing
- **Text Search**: $0.032 per request
- **Free tier**: $200/month credit (for first 90 days for new users)
- **After free tier**: Pay as you go

### Expected Costs
| Users/Month | Avg Errands | Google Calls | Cost |
|-------------|-------------|--------------|------|
| 10 | 3 | 30 | $0.96 |
| 50 | 3 | 150 | $4.80 |
| 100 | 3 | 300 | $9.60 |
| 500 | 3 | 1500 | $48.00 |

**Notes:**
- Google Places is only called when OSM fails (not every time)
- Retail chains will use Google Places more
- Set budget alerts to avoid surprise bills

## Monitoring Usage

1. Go to: **APIs & Services** → **Dashboard**
2. Click on **"Places API"**
3. View traffic, errors, and quota usage

## Troubleshooting

### "API key not valid"
- Make sure you enabled Places API
- Check API restrictions allow Places API
- Wait 5 minutes after creating key

### "This API project is not authorized"
- Enable billing on your project
- Check that Places API is enabled

### Costs too high?
- Reduce usage by improving OSM results first
- Set lower budget alerts
- Consider using free tier OSM + Tavily only

## Security Best Practices

1. **Never commit API keys to git** - Use `.env` file
2. **Restrict API key** - IP addresses + API restrictions
3. **Set budget alerts** - Prevent surprise bills
4. **Rotate keys periodically** - Every 90 days
5. **Monitor usage** - Check dashboard weekly

---

**Questions?** Check the official docs: https://developers.google.com/maps/documentation/places/web-service/overview

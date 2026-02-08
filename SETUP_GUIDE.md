# Orbit - Enhanced Place Resolution Setup Guide

## What Changed

We've upgraded Orbit's place resolution system to fix the issue where it was finding places in California and Ireland instead of local stores. The new system uses a 3-tier strategy:

### Multi-Tier Place Resolution Strategy

1. **Tier 1: OpenStreetMap (OSM) - FREE**
   - Searches nearby with tighter radius (10 miles default)
   - Filters out results outside USA and beyond 25 miles
   - Fast and free, works for ~60% of queries

2. **Tier 2: Google Places API - PAID ($0.032/search)**
   - Kicks in when OSM fails or for retail chains
   - Best accuracy for businesses (Target, CVS, Carter's, etc.)
   - Has complete database of US retail chains
   - ~30% of queries use this
   - Cost: ~$0.032 per search

3. **Tier 3: Gemini Flash 2.0 - FREE (up to 1500 req/day)** [Optional]
   - Validates remaining ambiguous results
   - Understands context and filters wrong matches
   - Only used if Google Places also uncertain

4. **Tier 4: Tavily Web Search - PAID FALLBACK** [Optional]
   - Final fallback when all else fails
   - ~5% of queries need this
   - Cost: ~$0.005 per search

## Cost Estimate

For **100 active users per month**:
- Tier 1 (OSM): **$0** (always free)
- Tier 2 (Google Places): **~$10/month** (100 users × 3 errands × 30% use rate × $0.032)
- Tier 3 (Gemini): **$0** (free tier: 1500 req/day)
- Tier 4 (Tavily): **~$5/month** (selective fallback use)

**Total: ~$15/month** for 100 users

**With $200 Google free credit**: First 6000+ searches are FREE!

## Setup Instructions

### 1. Get API Keys

#### Google Places API Key (Required - FREE $200 credit)
1. **See detailed guide**: `GOOGLE_PLACES_SETUP.md`
2. **Quick steps**:
   - Go to: https://console.cloud.google.com/
   - Create project → Enable Places API → Create API key
   - Set budget alerts ($20/month recommended)
3. **Free credit**: $200/month for first 90 days (new users)

#### Gemini API Key (Optional - FREE)
1. Go to: https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key
4. Free tier: 1500 req/day

#### Tavily API Key (Optional)
1. Go to: https://app.tavily.com/
2. Sign up for free account
3. Get your API key from dashboard
4. Free tier: 1000 searches/month

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your keys:

```env
# Gemini API Key (required for LLM validation)
GEMINI_API_KEY=your_gemini_api_key_here

# Tavily API Key (optional - for web search fallback)
TAVILY_API_KEY=your_tavily_api_key_here
```

### 3. Install Dependencies

```bash
# Install new dependencies
uv sync

# Or if using pip
pip install -r requirements.txt
```

New packages added:
- `python-dotenv` - for environment variables
- `google-generativeai` - for Gemini LLM
- `tavily-python` - for web search fallback

### 4. Test Locally

```bash
uv run streamlit run src/orbit/app.py
```

Try searching for:
- "Target" (should find local Target stores)
- "CVS" (should find local CVS)
- "Starbucks" (should find nearby Starbucks)

### 5. Deploy to Streamlit Cloud

#### Add Secrets to Streamlit Cloud

1. Go to your app settings: https://share.streamlit.io/
2. Click on your app → Settings → Secrets
3. Add your API keys in TOML format:

```toml
GEMINI_API_KEY = "your_gemini_api_key_here"
TAVILY_API_KEY = "your_tavily_api_key_here"
```

4. Save and redeploy

## How It Works

### Example: User searches for "Target"

**Without LLM (Old System):**
- OSM returns: Target (California), Target (Ireland), Target Shooting Range
- User confused, picks wrong one or gives up

**With LLM (New System):**
1. OSM returns same results
2. Gemini analyzes: "User in Chicago wants retail store, not shooting range"
3. Filters out California/Ireland (too far)
4. Picks local Target store
5. Auto-selects with confidence

### Fallback Chain

```
User searches "Target"
    ↓
[Tier 1] OSM search (10mi radius)
    ↓ Has results?
    ├─ Yes → [Tier 2] Gemini validates
    │            ↓ High confidence?
    │            ├─ Yes → ✅ Auto-select
    │            └─ No → Show options to user
    └─ No → [Tier 3] Tavily web search
                ↓ Found?
                ├─ Yes → ✅ Use result
                └─ No → ❌ Not found
```

## Features Removed (Temporarily)

We removed the **purpose** and **business hours** UI fields because:
- They were creating UI clutter
- Users weren't using them much
- We'll add them back later with better UX

## What to Test

1. **Common chains**: Target, Walmart, CVS, Starbucks, McDonald's
2. **Local businesses**: "Joe's Pizza", "Main Street Pharmacy"
3. **Misspellings**: "Targit", "Walmrt", "Starbux"
4. **Addresses**: "123 Main St" (should still work)

## Monitoring Costs

### Gemini (Free Tier)
- Dashboard: https://aistudio.google.com/app/apikey
- Free limit: 1500 requests/day
- If you exceed: $0.001-0.003 per request

### Tavily
- Dashboard: https://app.tavily.com/
- Free tier: 1000 searches/month
- Paid: $0.005 per search

## Troubleshooting

### "API key not found" error
- Make sure `.env` file exists in project root
- Check that keys are quoted properly in `.env`
- Restart Streamlit after adding keys

### "Module not found" error
- Run `uv sync` or `pip install -r requirements.txt`
- Make sure you're in the project directory

### Still getting wrong results
- Check that Gemini API key is set correctly
- Look at app logs to see which tier was used
- Consider lowering `OSM_SEARCH_RADIUS_MILES` in config.py

## Cost Control

To limit costs:

1. **Set Gemini quota** (if needed):
   - Go to Google Cloud Console
   - Set daily request limit

2. **Disable Tavily** (if too expensive):
   - Remove `TAVILY_API_KEY` from `.env`
   - System will fall back to user selection

3. **Tighter radius** (reduce API calls):
   - Edit `config.py`
   - Set `OSM_SEARCH_RADIUS_MILES = 5`

## Next Steps

1. Test with real users
2. Monitor API usage and costs
3. Collect feedback on accuracy
4. Consider adding:
   - Auto-fetch business hours from Google Places
   - Smart purpose detection
   - Multi-day planning

## Support

If you encounter issues:
1. Check logs: `streamlit run` output
2. Verify API keys are set
3. Test with simple queries first ("Target")
4. Check that dependencies installed correctly

---

**Summary**: The app now uses AI to understand what you're searching for and finds the right local place, not random results from across the world. Cost is minimal (~$15-20/month for 100 users) and can be scaled down if needed.

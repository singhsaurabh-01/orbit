# Deploying Orbit to Streamlit Cloud

## Prerequisites

- Your Orbit repo pushed to GitHub (public or private)
- A free Streamlit Cloud account (https://share.streamlit.io)

## Step 1: Push These New Files to GitHub

Make sure these files are committed and pushed:

```
requirements.txt          # Dependencies for Streamlit Cloud
.streamlit/config.toml    # Theme + server config
```

Also confirm your `.gitignore` does NOT block `.streamlit/` (it doesn't currently).

## Step 2: Deploy on Streamlit Cloud

1. Go to https://share.streamlit.io
2. Click **"New app"**
3. Select your GitHub repo (`orbit`)
4. Set these fields:
   - **Branch:** `main` (or whatever your default branch is)
   - **Main file path:** `src/orbit/app.py`
   - **Python version:** 3.11
5. Click **"Deploy"**

That's it. Streamlit Cloud will install dependencies from `requirements.txt` and start the app.

## Step 3: Get Your Shareable URL

Once deployed, you'll get a URL like:
```
https://orbit-[your-username].streamlit.app
```

This is what you share with test users.

## Important Notes

### Database is Ephemeral
- SQLite data resets when the app reboots or redeploys
- This is fine for now — each user session starts fresh
- Users won't lose anything important (plans are generated on the fly)

### API Rate Limits
- Nominatim (geocoding): 1 request/second — already enforced in code
- OSRM (routing): Public server, be mindful of heavy usage
- For 10-20 test users, this is fine

### Cost
- Streamlit Cloud free tier: 1 app, unlimited viewers
- No credit card needed

## Sharing With Test Users

Send them this message:

> "Hey! I'm building a day planner app called Orbit that helps you plan the best route for your errands. Would you try it out and give me feedback? Here's the link: [YOUR_URL]
>
> Just enter your home address, add 3-5 errands, and hit Generate Plan. Takes about 2 minutes. Let me know what you think!"

## Collecting Feedback

Options (simplest to most structured):
1. **Google Form** — create a 5-question feedback form, link it from the app
2. **In-app feedback** — add a simple text input at the bottom of the app
3. **Direct messages** — just ask people to text/DM you their thoughts

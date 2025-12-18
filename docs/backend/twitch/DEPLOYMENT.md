# Twitch Bot Deployment Guide

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python main.py
```

## Docker Deployment

### Build and run with Docker Compose

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Build and run with Docker

```bash
# Build image
docker build -t niibot-twitch .

# Run container
docker run -d \
  --name niibot-twitch \
  -p 4343:4343 \
  --env-file .env \
  niibot-twitch

# View logs
docker logs -f niibot-twitch

# Stop container
docker stop niibot-twitch
docker rm niibot-twitch
```

## Deploy to Render

1. Create a new **Web Service** on Render
2. Connect your GitHub repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `python main.py`
5. Add environment variables from `.env`:
   - `CLIENT_ID`
   - `CLIENT_SECRET`
   - `BOT_ID`
   - `OWNER_ID`
   - `DATABASE_URL`
   - `OPENROUTER_API_KEY`
   - `OPENROUTER_MODEL`
   - `OAUTH_REDIRECT_URI=https://your-app.onrender.com/oauth/callback`
6. Update Twitch Developer Console with the new redirect URI

## Important Notes

- **Port 4343**: TwitchIO AutoBot uses this port for OAuth callbacks
- **OAUTH_REDIRECT_URI**: Must match your deployment URL
- **LOG_LEVEL**: Use `INFO` for production (default)
- **Database**: Configure PostgreSQL connection URL

## OAuth Setup for Remote Deployment

When deployed to a public server:

1. Get your public URL (e.g., `https://your-app.onrender.com`)
2. Set in environment variables: `OAUTH_REDIRECT_URI=https://your-app.onrender.com/oauth/callback`
3. Add this URL to [Twitch Developer Console](https://dev.twitch.tv/console) → OAuth Redirect URLs
4. Generate new OAuth URLs: `python scripts/oauth.py`
5. Re-authorize Bot and Broadcaster accounts using the new URLs

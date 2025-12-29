# Niibot API Server

FastAPI server for frontend integration.

## Structure

```
backend/api/
├── main.py              # FastAPI application
├── config.py            # Environment variables
├── routers/
│   ├── auth.py          # Authentication routes
│   └── channels.py      # Channel monitoring routes
└── services/
    ├── auth.py          # JWT authentication
    ├── twitch.py        # Twitch OAuth & API
    ├── user.py          # User info
    ├── channel.py       # Channel management
    └── database.py      # PostgreSQL connection pool
```

## API Endpoints

### Authentication (`/api/auth`)
- `GET /api/auth/twitch/oauth` - Get Twitch OAuth URL
- `GET /api/auth/twitch/callback` - OAuth callback, set JWT cookie
- `GET /api/auth/user` - Get current user (requires JWT)
- `POST /api/auth/logout` - Logout

### Channels (`/api/channels`)
- `GET /api/channels/monitored` - Get monitored channels with live status
- `GET /api/channels/my-status` - Get current user's channel subscription status
- `POST /api/channels/toggle` - Enable/disable channel monitoring

### Health
- `GET /api/health` - Health check
- `GET /` - API info
- `GET /docs` - Swagger documentation

## Environment Variables

Create `backend/api/.env`:

```env
CLIENT_ID=your_twitch_client_id
CLIENT_SECRET=your_twitch_client_secret
JWT_SECRET_KEY=your_random_secret_key
DATABASE_URL=postgresql://user:pass@host:5432/dbname
FRONTEND_URL=http://localhost:3000
API_URL=http://localhost:8000
LOG_LEVEL=INFO
```

## Run

```bash
cd backend/api
python main.py
```

Server runs at `http://localhost:8000`

## Authentication Flow

1. User authorizes → Twitch returns code
2. API exchanges code for access_token + user_id
3. API saves token to database
4. API creates JWT and sets HTTP-only cookie
5. Subsequent requests use JWT for authentication

## Security

- HTTP-only cookies prevent XSS
- SameSite protection against CSRF
- Environment-based secure flag (production vs development)
- JWT with HS256 algorithm
- Required environment variables validation

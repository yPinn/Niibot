# Niibot API Endpoints

## Base Configuration

- Base URL: `http://localhost:8000` (development)
- Authentication: Cookie-based (httponly)
- Content-Type: `application/json`

---

## Authentication

| Method | Path | Description | Frontend Function |
|--------|------|-------------|-------------------|
| GET | `/api/auth/twitch/oauth` | Get Twitch OAuth URL | `getTwitchOAuthUrl()` |
| GET | `/api/auth/twitch/callback` | OAuth callback handler | Auto redirect |
| GET | `/api/auth/user` | Get current user info | `getCurrentUser()` |
| POST | `/api/auth/logout` | User logout | `logout()` |

**Example:**
```typescript
const user = await getCurrentUser()
// { id, name, display_name, avatar }

await logout()
```

---

## Channels

| Method | Path | Description | Frontend Function |
|--------|------|-------------|-------------------|
| GET | `/api/channels/monitored` | Get monitored channels | `getMonitoredChannels()` |
| GET | `/api/channels/my-status` | Get user channel status | `getMyChannelStatus()` |
| POST | `/api/channels/toggle` | Toggle bot status | `toggleChannel()` |

**Example:**
```typescript
const channels = await getMonitoredChannels()
// [{ id, name, display_name, avatar, is_live, viewer_count, game_name }]

const status = await getMyChannelStatus()
// { channel_id, bot_enabled }

const result = await toggleChannel('123456', true)
// { message: "Channel enabled successfully" }
```

**Request Body (toggle):**
```json
{
  "channel_id": "123456",
  "enabled": true
}
```

---

## Analytics

| Method | Path | Description | Frontend Function |
|--------|------|-------------|-------------------|
| GET | `/api/analytics/summary?days=30` | Get analytics summary | `getAnalyticsSummary(days)` |
| GET | `/api/analytics/top-commands?days=30&limit=10` | Get top commands | `getTopCommands(days, limit)` |
| GET | `/api/analytics/sessions/{id}/commands` | Get session commands | `getSessionCommands(sessionId)` |
| GET | `/api/analytics/sessions/{id}/events` | Get session events | `getSessionEvents(sessionId)` |

**Example:**
```typescript
const summary = await getAnalyticsSummary(30)
// { total_sessions, total_stream_hours, total_commands, total_follows,
//   total_subs, avg_session_duration, recent_sessions }

const topCommands = await getTopCommands(30, 10)
// [{ command_name, usage_count, last_used_at }]

const sessionCommands = await getSessionCommands(123)
// [{ command_name, usage_count, last_used_at }]

const events = await getSessionEvents(123)
// [{ event_type, user_id, username, display_name, metadata, occurred_at }]
```

---

## Stats

| Method | Path | Description | Frontend Function |
|--------|------|-------------|-------------------|
| GET | `/api/stats/channel` | Get channel statistics | `getChannelStats()` |

**Example:**
```typescript
const stats = await getChannelStats()
// { top_commands: [{ name, count }],
//   top_chatters: [{ username, message_count }],
//   total_messages, total_commands }
```

---

## Commands

| Method | Path | Description | Frontend Function |
|--------|------|-------------|-------------------|
| GET | `/api/commands/components` | Get all bot components | `getComponents()` |

**Example:**
```typescript
const components = await getComponents()
// { discord: [...], twitch: [...], total: 10 }
```

---

## Health Check

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check endpoint |
| GET | `/` | API root info |

**Response:**
```json
// GET /api/health
{
  "status": "ok",
  "service": "niibot-api",
  "version": "2.0.0",
  "environment": "development"
}

// GET /
{
  "service": "Niibot API",
  "version": "2.0.0",
  "docs": "/docs",
  "health": "/api/health"
}
```

---

## Error Handling

Standard HTTP error codes:

- `400` - Bad request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not found
- `500` - Internal server error

**Error Response:**
```json
{
  "detail": "Error message"
}
```

---

## Documentation

- Swagger UI: http://localhost:8000/docs (development only)
- ReDoc: http://localhost:8000/redoc (development only)

---

## Type Definitions

Frontend type definitions:
- `frontend/src/api/analytics.ts` - Analytics types
- `frontend/src/api/channels.ts` - Channels types
- `frontend/src/api/commands.ts` - Commands types
- `frontend/src/api/stats.ts` - Stats types
- `frontend/src/api/user.ts` - User types

---

## Notes

1. All endpoints except `/api/auth/twitch/oauth` and `/api/health` require authentication
2. CORS is configured for frontend cross-origin requests
3. Use `credentials: 'include'` to send cookies
4. Some frontend functions use caching (see `apiCache`)

---

Last updated: 2026-01-08

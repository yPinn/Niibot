# Niibot Project

## Project Structure

- **Backend**: Python/FastAPI — `backend/`
- **Frontend**: React/TypeScript — `frontend/`
- **Discord Bot**: discord.py — `backend/discord/`
- **Twitch Bot**: TwitchIO — `backend/twitch/`

## Deployment

- Backend: Docker
- Frontend: Cloudflare Pages
- Auth: Twitch OAuth via backend JWT cookie sessions (Discord dashboard OAuth removed)

## Git Workflow (GitHub Flow + staging)

### Branch Strategy

| Branch      | Environment         | Deploy              |
| ----------- | ------------------- | ------------------- |
| `main`      | Production (正式區) | Manual / CD trigger |
| `staging`   | Testing (測試區)    | Manual / CD trigger |
| `feature/*` | Local dev           | —                   |
| `fix/*`     | Local dev           | —                   |

### Standard Feature Flow

```text
feature/xxx  ──PR──►  staging  ──(QA pass)──PR──►  main
```

1. Branch off `staging`: `git checkout -b feature/xxx staging`
2. Develop and commit locally
3. Push and open PR → `staging`
4. Test on staging environment
5. When confirmed stable → open PR `staging` → `main`
6. Merge to `main` triggers production deploy

### Hotfix Flow

```text
hotfix/xxx  ──PR──►  main  ──PR──►  staging  (backport)
```

### Docker Compose per Environment

Each environment uses `docker-compose.yml` (base, no host ports) plus its own overlay:

```bash
# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml [--profile <name>] up -d

# Staging (isolated project, separate containers/network/volumes)
docker compose -p niibot-staging --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.staging.yml [--profile <name>] up -d

# Local dev
docker compose -f docker-compose.yml -f docker-compose.dev.yml [--profile <name>] up
```

Port table:

| Service | Base | Prod | Dev | Staging |
| ------- | ---- | ---- | --- | ------- |
| api | — | 8000 | 8000 | 8001 |
| postgres | — | — | 5433 | 5434 |
| scrapling | — | — | 3001 | 3003 |
| instafix | — | — | 3002 | 3004 |

### Environment Variables

| File                   | Purpose                           |
| ---------------------- | --------------------------------- |
| `.env`                 | Production secrets (never commit) |
| `.env.staging`         | Staging secrets (never commit)    |
| `.env.example`         | Template for production           |
| `.env.staging.example` | Template for staging              |

### Branch Protection (set on GitHub)

- `main`: require PR + 1 approval, no direct push
- `staging`: require PR, allow direct push for solo dev

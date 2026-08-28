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

## Admission & Tenancy

Niibot is multi-tenant — each Twitch broadcaster's channel is a separate
tenant. Three concerns are deliberately split across distinct services; do
NOT couple them inside routers or repositories:

- **IdentityService** — find_or_link by `(platform, platform_user_id)`,
  self-heals when an identity row goes missing via reconciliation. Replaces
  the deprecated `oauth_service.find_or_create_user`.
- **AdmissionService** — owns the `memberships.status` state machine
  (`pending | active | suspended | rejected`); every transition writes a
  matching `membership_events` row (append-only, DB-enforced immutable).
- **TenantService** — channel ownership + per-channel RBAC via
  `channel_members`. Use `require_tenant_access` or `require_self_tenant_access`
  FastAPI dependencies on channel-scoped endpoints.

Full design + rollout notes:
[docs/architecture/admission-and-tenancy.md](docs/architecture/admission-and-tenancy.md).

Key invariants:

- The OAuth callback must NOT create `activation_requests` rows for existing
  users. Reauth idempotency is enforced by IdentityService's fast path.
- `users.is_activated` and the `activation_requests` table are LEGACY and
  retained only for rollback safety; `memberships` is the source of truth.
- Channel-scoped tables must always filter by `channel_id`. Postgres RLS
  policies in migration 083 act as a second line of defence (left disabled
  until full router migration).
- `channels.enabled` is DB-gated to admission (migration 084): a channel may be
  `enabled=TRUE` only while its owner's `memberships.status = 'active'`. Triggers
  enforce this and fire `channel_toggle`, so approve/suspend joins/parts the bot
  with no application call sites. Do not set `enabled=TRUE` from app code for a
  non-active owner — the trigger will override it.

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

### Docker Compose & Environments

Each environment = `docker-compose.yml` (base, no host ports) + its overlay
(`prod` / `staging` / `dev`), isolated by Compose project. `migrate` container
runs DB migrations on startup. Full commands, port table, and CI/CD secret sync:
[docs/guides/deployment.md](docs/guides/deployment.md).

### Environment Variables

`npm run nb -- env init` (alias for `bash scripts/env.sh init`) copies every
`*.env.example` → `*.env`. The single source of truth for every variable is
[docs/guides/environment.md](docs/guides/environment.md). Never commit a `.env`.

All dev/ops scripts share one entry point — `npm run nb -- <group> <command>`
(`npm run nb -- --help`). See [scripts/README.md](scripts/README.md).

### Branch Protection (set on GitHub)

- `main`: require PR + 1 approval, no direct push
- `staging`: require PR, allow direct push for solo dev

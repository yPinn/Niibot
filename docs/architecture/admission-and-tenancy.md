# Admission & Tenancy Model

> Last updated: 2026-06-11 — covers migrations 076–083 and the IdentityService /
> AdmissionService / TenantService introduced in the same release.

This document is the source of truth for how identity, admission (approval to
use the bot), and tenancy (per-channel isolation) work in Niibot. Read this
before changing anything in `services/identity_service.py`,
`services/admission_service.py`, `services/tenant_service.py`, the OAuth
callback, or the activation flow.

## Why this exists

The previous design coupled three concerns inside one OAuth callback:

1. _Identity_: which Twitch user is this?
2. _Admission_: are they allowed to use the bot?
3. _Tenant setup_: do we have a `channels` row + token for them?

The coupling caused a bug where reauth (token expiry, scope upgrade, or any
data drift that lost the `user_linked_accounts` row) silently created a new
`users` row, a new `activation_requests`, and orphaned the operator's old
data — so admins saw "ghost" pending approvals for users they had already
approved months ago.

The fix separates the four concerns into purpose-built services, makes every
state transition idempotent + audited, and adds a tenant boundary that scales
to mod delegation when needed.

## Domain model

Four concepts, each owning its own data:

| Concept        | Table                               | Answers                                          |
| -------------- | ----------------------------------- | ------------------------------------------------ |
| **User**       | `users`                             | "Who is this person?"                            |
| **Identity**   | `identities`                        | "Which Twitch / Discord account are they on?"    |
| **Membership** | `memberships` + `membership_events` | "Are they allowed to use the product?"           |
| **Tenant**     | `channels` + `channel_members`      | "Whose workspace is this and who can manage it?" |
| **Credential** | `tokens` (+ `tokens.identity_id`)   | "Can we call platform APIs for them?"            |

Invariants that hold across the whole system:

- One **User** ↔ many **Identities** (multi-platform aware; Discord rollout
  adds rows without touching admission).
- **Membership** is user-level (User-wide; not per-platform).
- **Membership** state is a `pending | active | suspended | rejected` enum, NOT
  a boolean. Every transition is audited in `membership_events`.
- **Tenant** = one `channels` row. Owner is `channels.owner_user_id`. Per-tenant
  roles live in `channel_members` (`owner | manager | viewer`).
- All tenant-scoped tables (`commands`, `crosshairs`, `timers`, ...) filter
  by `channel_id`. Postgres RLS policies in migration 083 enforce this at the
  DB layer as a second line of defence (disabled by default until rollout).

## Service layer

```text
┌──────────────────────────────────────────────────────┐
│ Routers (auth_router, admin_router, channels_router) │
└─────────────────────┬────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│ IdentityService    — find_or_link + reconciliation   │
│ AdmissionService   — state machine + audit log       │
│ TenantService      — tenant lifecycle + access checks│
│ ChannelService     — credentials + channel ops       │
└─────────────────────┬────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│ Repositories (one per table; pure SQL)               │
└──────────────────────────────────────────────────────┘
```

### IdentityService.find_or_link

Four code paths, in priority order:

1. **Fast path** — `(platform, platform_user_id)` already in `identities`.
   Touch `last_seen_at`, sync username if changed, emit `auth_events(reauth)`,
   return. **Does not touch admission.**
2. **Account-link path** — `link_to_user_id` argument given. Insert the new
   identity against the supplied user. Used by the future "Link Discord"
   button in the dashboard.
3. **Reconciliation path** — identity missing, but `channels.owner_user_id`
   (or `activation_codes.used_by_user_id`) remembers the previous owner.
   Re-insert the identity against that user. **This is the bug fix.**
4. **Fresh signup** — none of the above match. Create new `users` + new
   `identities` in a transaction; let the unique constraint resolve concurrent
   first-time signups.

### AdmissionService

Owns the state machine:

```text
                ensure_pending()
       [none] ────────────────► pending
                                   │
              approve() / OTP      │
                ┌──────────────────┘
                ▼
              active ◄─────────── reinstate()
                │                       ▲
                │ suspend()             │
                ▼                       │
              suspended ────────────────┘

         pending ──reject()──► rejected
                                   │
                              reapply()
                                   ▼
                                pending
```

Every transition:

- Reads `memberships` to short-circuit no-op cases (idempotency).
- Opens a transaction.
- Calls `MembershipRepository.upsert_status(... conn=conn)`.
- Calls `MembershipRepository.insert_event(... conn=conn)`.
- Commits.

The trigger `trg_membership_events_no_update` (migration 077) makes
`membership_events` append-only at DB level so application bugs cannot
rewrite history.

### TenantService

Three responsibilities:

- `ensure_tenant_for_owner(channel_id, owner_user_id, ...)` — idempotent
  bootstrap called from the OAuth callback. Inserts/updates the `channels`
  row and seeds `channel_members(role='owner')`.
- `assert_access(channel_id, user_id, required_role)` — verifies the caller
  has at least the required role; raises `TenantNotFoundError` /
  `TenantSuspendedError` / `TenantAccessDeniedError`. Used by the `require_tenant_access` and
  `require_self_tenant_access` FastAPI dependencies.
- `bind_session(conn, channel_id)` — sets the `app.current_channel_id` GUC so
  Postgres RLS policies match. Call within a transaction; no-op if RLS is
  disabled.

## Request flow: OAuth callback

```text
POST /api/auth/twitch/callback
  │
  ├─ exchange_code_for_token         (twitch_api)
  ├─ ChannelService.save_token       (upsert tokens + channels.channel_name)
  ├─ IdentityService.find_or_link    (1 of 4 branches; emits auth_event)
  │     └─ result.is_new_user?
  │             yes → AdmissionService.ensure_pending(user)  + 'requested' event
  │             no  → no admission write     ← fixes the bug
  ├─ owner_id == platform_user_id?
  │     yes → AdmissionService.auto_admit(user, reason='owner')
  ├─ TenantService.ensure_tenant_for_owner   (idempotent channel + owner row)
  └─ set auth_token cookie; redirect /dashboard
```

Key property: reauth for an already-active user only touches `tokens`,
`identities.last_seen_at`, and `auth_events`. `memberships` and
`membership_events` are untouched.

## Request flow: feature endpoint with tenant scope

Two dependencies exist:

- `require_self_tenant_access` — channel_id is the caller's own Twitch
  broadcaster_id (from JWT). Use for legacy endpoints that don't take
  channel_id in the URL.
- `require_tenant_access` — channel_id comes from a `{channel_id}` path
  parameter. Use for new endpoints that need to support mod delegation or
  multiple channels per user.

Both verify `channel_members` membership, both raise the same exception
types, both return a `TenantContext`. Migration pattern from the legacy
`get_current_channel_id` shim (still working):

```python
# Before
async def list_commands(
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(...),
):
    return await service.list_commands(channel_id)

# After
async def list_commands(
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommandConfigService = Depends(...),
):
    return await service.list_commands(ctx.channel_id)
```

Exemplars already migrated:

- `POST /api/channels/twitch/toggle` (state mutation; high-risk)
- `POST /api/commands/configs` (config creation)

The remaining channel-scoped endpoints (~30 across 14 routers) still use the
legacy shim. They behave identically today; migrating them adds proper
`channel_members` enforcement (matters for mod delegation and tenant
suspension). Migrate per-router in follow-up PRs.

### Test override SOP when migrating a router

Every PR that switches an endpoint from `get_current_channel_id` to
`require_self_tenant_access` (or `require_tenant_access`) MUST update the
corresponding `tests/api/test_*_router.py` in the same commit. The default
`get_token_payload` dependency hits the JWT cookie and DB; without an
override, every migrated endpoint's tests return 401.

```python
from core.dependencies import require_self_tenant_access
from services import TenantContext

def _make_client(...):
    app = FastAPI(...)
    app.include_router(_router)
    # ... existing overrides ...
    app.dependency_overrides[require_self_tenant_access] = lambda: TenantContext(
        channel_id=CHANNEL_ID, user_id=_OWNER_USER_UUID, role="owner",
    )
```

`TenantContext` is a frozen dataclass exported from `services`. The role
field can be `'owner' | 'manager' | 'viewer'` — pick whichever the endpoint
expects to gate on.

## Schema rollout

Migrations applied in order (each is reversible only by hand — plan
accordingly):

| #   | Purpose                                                                                                                  |
| --- | ------------------------------------------------------------------------------------------------------------------------ |
| 076 | Rename `user_linked_accounts → identities`; add `id`, `linked_at`, `last_seen_at`; create compat view                    |
| 077 | `memberships` + `membership_events` + `auth_events` + immutability trigger                                               |
| 078 | `channels.owner_user_id`, `suspended_at`, `suspended_reason` + `channel_members` table                                   |
| 079 | `tokens.identity_id` FK (nullable; populated by 082)                                                                     |
| 080 | Backfill: legacy `users.is_activated` + `activation_requests` + `activation_codes` → `memberships` + `membership_events` |
| 081 | Backfill: `channels.owner_user_id` via identities lookup; seed `channel_members(role='owner')`                           |
| 082 | Backfill: `tokens.identity_id` via identities lookup                                                                     |
| 083 | RLS policies created but DISABLED; flip on per-table after staging shakedown                                             |

**Rollback safety:** legacy columns (`users.is_activated`,
`activation_requests`) are retained during the rollout for dual-read fallback.
Drop them in a follow-up migration after one or two stable releases.

## Things this design intentionally does NOT do

- **No per-user-per-platform admission.** A user admitted via Twitch is also
  admitted on Discord. Per-platform gating would require splitting the
  Membership concept and is not justified by current product needs.
- **No CQRS / event sourcing.** `membership_events` is an audit log, not the
  source of truth — `memberships.status` is. Reading the log to derive state
  is allowed; rebuilding the table from it on every boot is not.
- **No tenant-level billing / metering.** No payment flow exists; revisit when
  it does.
- **No automatic mod delegation.** `channel_members` is schema-ready but no UI
  exists yet. Adding the UI does NOT require schema changes.
- **No RLS enabled by default.** Policies exist but `ALTER TABLE ... ENABLE
ROW LEVEL SECURITY` is left to the operator after they confirm
  `TenantService.bind_session` is wired into every request handler.

## Open follow-up work

- Migrate the remaining 12 channel-scoped routers to `require_self_tenant_access`.
- Surface the membership timeline in the admin UI (the backend endpoint
  `GET /api/admin/memberships/{user_id}/timeline` exists; frontend component
  pending).
- Wire `TenantService.bind_session` into the FastAPI request middleware so the
  RLS GUC is set automatically once policies are enabled.
- Drop legacy `users.is_activated` + `activation_requests` after two stable
  releases on the new model.
- Add the "Link Discord" account-linking flow (the `IdentityService.find_or_link`
  `link_to_user_id` argument is already wired).

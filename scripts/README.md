# scripts/

Two locations, one entry point:

- **`scripts/`** — repo-wide ops (env files span every service, `env.registry.toml`
  lives at the repo root, staging compose is repo-level, CI helpers). Mostly bash.
- **`backend/scripts/`** — backend dev tools (DB, Twitch/Discord, backfills). Python.

Everything is reachable through one command:

```bash
npm run nb -- <group> <command> [options]      # from repo root
```

`npm run nb -- --help` lists groups; `npm run nb -- <group> --help` lists a group's
commands. Each script also still runs standalone (see the last column) — `nb` is a
thin dispatcher that lazy-imports one script per call.

## Env files: two stages

1. `nb env gen` — regenerate `*.env.example` templates + `env.manifest.json` +
   the docs table from `env.registry.toml` (the single source of truth).
2. `nb env init` — copy every `*.env.example` → `*.env` so you can fill in secrets.

`nb env snapshot` / `backup` / `restore` / `diff` manage timestamped copies of the
live (secret-filled) files under `data/`.

## Commands

| `nb` command                                                       | does                                                            | standalone                                                        |
| ------------------------------------------------------------------ | --------------------------------------------------------------- | ----------------------------------------------------------------- |
| `db migrate [--dry] [--env staging]`                               | run pending migrations                                          | `uv run --directory backend python scripts/db_migrate.py`         |
| `db check [--env staging]`                                         | verify NOTIFY triggers / schema / migrations                    | `… scripts/db_check.py`                                           |
| `db seed [channel_id] [n]`                                         | **[dev]** generate fake session/viewer data                     | `… scripts/dev/db_seed.py`                                        |
| `db clear [-y]`                                                    | **[dev]** wipe analytics/session tables (confirms first)        | `… scripts/dev/db_clear.py`                                       |
| `db backup`                                                        | `pg_dump` via docker                                            | `bash backend/scripts/db_backup.sh`                               |
| `twitch oauth [--role bot\|broadcaster] [--env staging]`           | generate a bot/broadcaster token (interactive if flags omitted) | `… scripts/twitch_oauth.py`                                       |
| `twitch tokens [--env staging]`                                    | list stored tokens, validate, show scopes                       | `… scripts/twitch_diag.py tokens`                                 |
| `twitch emotes [--env staging]`                                    | bot emote access per channel                                    | `… scripts/twitch_diag.py emotes`                                 |
| `twitch backfill-sessions [--limit N] [--keep-existing]`           | backfill sessions from Twitch VODs                              | `… scripts/twitch_backfill_sessions.py`                           |
| `twitch backfill-matcher [--days 7,30,90] [--dry-run]`             | backfill overlap tables from `chatter_stats`                    | `… scripts/twitch_backfill_matcher.py`                            |
| `discord ls\|diff\|sync\|rm [--prod] [--guild ID] [--global] [-y]` | manage Discord slash commands                                   | `… scripts/discord_cmds.py <cmd>`                                 |
| `models update [--with-uptime]`                                    | refresh `twitch/free_models.json` from OpenRouter               | `… scripts/models_update.py`                                      |
| `env init [-f]`                                                    | copy every `*.env.example` → `*.env`                            | `bash scripts/env.sh init`                                        |
| `env gen \| check \| print KEY`                                    | (re)generate env templates from `env.registry.toml`             | `python scripts/gen_env.py`                                       |
| `env snapshot \| backup \| restore \| diff \| list \| clean`       | snapshot / restore live env files                               | `bash scripts/env.sh <cmd>`                                       |
| `staging up\|down\|reset\|build\|logs\|ps\|restart\|migrate\|exec` | staging docker-compose wrapper                                  | `bash scripts/staging.sh <cmd>`                                   |
| `badges`                                                           | download Twitch role-badge images to `frontend/public/`         | `python scripts/badges.py`                                        |

## Not wrapped by `nb` (CI / one-off only)

- `scripts/ci_write_env.sh` — CI writes runner env files from `env.manifest.json`
- `backend/scripts/migrate_runtime_data.sh` — one-off `data/` → `runtime/` move (deploy workflow)

## Adding a command

1. Write `scripts/<name>.py` with `build_parser()` + `run(args) -> int` + a
   `if __name__ == "__main__": raise SystemExit(main())` block.
2. Use helpers from `backend/scripts/_lib.py` (`load_env`, `db_conn`/`db_pool`,
   `add_env_arg`, `confirm`, `utf8_stdio`) — don't re-roll `load_dotenv` / `sys.path`.
3. Register a subparser + `_run_py("<name>")` handler in `backend/scripts/nb.py`.
4. Add a row to the table above.

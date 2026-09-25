# Scripts

Use one public entry point from the repository root:

```bash
npm run nb -- <group> <command> [options]
```

Run `npm run nb -- --help` or `npm run nb -- <group> --help` for the current
surface. Leaf scripts remain executable for CI and recovery work.

## Layout

- `scripts/env/`, `scripts/ci/`, `scripts/assets/`: repository-wide tooling.
- `backend/scripts/<domain>/<verb>.py`: backend operations.
- `scripts/stack.sh`: environment-scoped Compose wrapper.
- `.github/{push,pull}.sh`: local GitHub Actions configuration sync.

Files use short domain and verb names. `twitch_ops` and `discord_ops` intentionally
avoid shadowing the runtime `twitch` package and third-party `discord` package.

## Commands

| `nb` command                                                  | Purpose                                        | Direct entry                                      |
| ------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------- |
| `db migrate [--dry] [--env dev\|stg\|prod]`                   | Apply migrations                               | `python -m scripts.db.migrate`                    |
| `db check [--env …]`                                          | Check schema, triggers, and migrations         | `python -m scripts.db.check`                      |
| `db seed [channel_id] [n]`                                    | Seed dev data                                  | `python -m scripts.db.seed`                       |
| `db clear [-y]`                                               | Clear dev analytics/session data               | `python -m scripts.db.clear`                      |
| `db backup [--env …]`                                         | Dump PostgreSQL through Compose                | `bash backend/scripts/db/backup.sh <env>`         |
| `twitch oauth --env dev`                                      | Run local OAuth callback                       | `python -m scripts.twitch_ops.oauth`              |
| `twitch tokens\|emotes [--env …]`                             | Diagnose stored Twitch access                  | `python -m scripts.twitch_ops.diag <action>`      |
| `twitch credentials [--dry-run] [--repair-missing-envelopes]` | Encrypt or repair credentials                  | `python -m scripts.twitch_ops.credentials`        |
| `twitch backfill-sessions`                                    | Backfill sessions from VODs                    | `python -m scripts.twitch_ops.backfill_sessions`  |
| `twitch backfill-matches`                                     | Backfill chatter overlap tables                | `python -m scripts.twitch_ops.backfill_matches`   |
| `discord ls\|diff\|sync\|rm [--env …]`                        | Manage Discord commands                        | `python -m scripts.discord_ops.commands <action>` |
| `checkin backfill`                                            | Backfill historical collection draws           | `python -m scripts.checkin.backfill`              |
| `ai eval`                                                     | Run the role-play prompt gate                  | `python -m scripts.ai.eval`                       |
| `models update`                                               | Refresh the OpenRouter model list              | `python -m scripts.models.update`                 |
| `assets collections preview\|build`                           | Build collection card assets                   | `python -m scripts.assets.collections <action>`   |
| `badges [--env …]`                                            | Download Twitch badge assets                   | `python scripts/assets/badges.py`                 |
| `stack <env> <command>`                                       | Operate one Compose project; `config` is quiet | `bash scripts/stack.sh <env> <command>`           |

Direct Python entries run under `uv run --directory backend` unless their path is
under root `scripts/`.

## Environment commands

`env.registry.toml` is the source of truth for runtime and GitHub examples.

| Command                                            | Purpose                                               |
| -------------------------------------------------- | ----------------------------------------------------- |
| `env gen`                                          | Generate examples, manifest, and the env docs table   |
| `env check`                                        | Check generated-file drift                            |
| `env validate <dev\|stg\|prod\|gh-stg\|gh-prod>`   | Check structure, required values, and complete groups |
| `env print KEY`                                    | Show one registry entry                               |
| `env init [dev\|stg\|prod] [-f]`                   | Create one explicit runtime set; defaults to dev      |
| `env migrate <dev\|stg\|prod>`                     | Rename legacy files; refuses source/target collisions |
| `env sync <dev\|stg\|prod\|gh> [--check]`          | Reorder local files and preserve known values         |
| `env sync dev --from-stg`                          | Copy declared nonprod identities into local dev       |
| `env snapshot\|backup\|restore\|diff\|list\|clean` | Manage encryption-key-preserving local copies         |
| `env push <stg\|prod>`                             | Validate and push GitHub variables/secrets            |
| `env pull <stg\|prod>`                             | Pull variables and report secret presence             |

`env migrate` requires the target because legacy unsuffixed files did not reveal
whether they belonged to dev or prod. Run `env sync` after migration; it moves
known shared keys, refuses unknown/conflicting values without printing them, and
then `env validate` checks the result. `env sync gh` migrates all six local
GitHub files together; remove obsolete keys only after a snapshot with
`--drop-unknown`. `env sync dev --from-stg` overlays only registry entries marked
`nonprod_shared`; database, JWT, and encryption values remain dev-only.

## Compose environments

| Selector | Project       | Files                                | Published host ports                                        |
| -------- | ------------- | ------------------------------------ | ----------------------------------------------------------- |
| `dev`    | `niibot-dev`  | `compose.yaml` + `compose.dev.yaml`  | API 8000, DB 5432, Twitch 4344, Discord 8080, InstaFix 3002 |
| `stg`    | `niibot-stg`  | `compose.yaml` + `compose.stg.yaml`  | API 18001 only                                              |
| `prod`   | `niibot-prod` | `compose.yaml` + `compose.prod.yaml` | API 18000 only                                              |

All published ports bind to `127.0.0.1`. Database commands for stg/prod must run
inside the matching Compose network. Use `nb stack` or the npm dev commands;
the wrapper binds `NIIBOT_ENV`, the root env file, overlay, and service env files
to the same selector. Direct Compose calls fail when that selector is absent.

## Internal-only entries

- `scripts/ci/paths.py`: CI changed-path classifier.
- `scripts/env/ci.py`: tested deploy env renderer; `write_ci.sh` is its CI wrapper.
- `backend/scripts/runtime/migrate.sh`: one-time runtime-data migration.

## Adding a command

1. Add `backend/scripts/<domain>/<verb>.py` with `build_parser()` and `run(args)`.
2. Reuse helpers from `backend/scripts/_lib.py`.
3. Register the command in `backend/scripts/nb.py`.
4. Add dispatcher and behavior tests.

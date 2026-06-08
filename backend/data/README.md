# `backend/data/` — static repo content

This directory holds **read-only configuration baked into every Docker image**
via `COPY data/ ./data/` in each service Dockerfile. Edit a file here, push,
the next deploy ships it.

| Path | Used by | Notes |
|------|---------|-------|
| `chat_filter.json` | twitch AI | Substring + pinyin block list |
| `eat.json` | discord eat cog | Restaurant list |
| `embed.json` | discord (all cogs) | Default author/footer chrome |
| `fortune.json` | twitch + discord fortune | Lucky text pool |
| `free_models.json` | shared AI provider chain | OpenRouter free-tier roster |
| `games.json` | discord games cog | Game catalog |
| `giveaway.json` | discord giveaway cog | Static config (not active state) |
| `tarot.json` | twitch + discord tarot | 78-card deck |
| `knowledge_packs/*.md` | twitch AI | Per-pack keyword-matched injections |

## Sibling: `backend/runtime/`

`backend/runtime/` holds **mutable state** the bot writes at run time
(log channel mappings, in-flight giveaway state, etc.). It is volume-mounted
per environment so each deployment keeps its own state.

| Path | Used by | Notes |
|------|---------|-------|
| `log_channels.json` | discord events cog | Guild → log channel map |
| `giveaway_state.json` | discord giveaway cog | Active giveaway snapshots |

## Conventions

- **Adding a new static file** → drop the file here, code uses `DATA_DIR /
  "your_file.json"`, push. No host-side seeding required on staging/prod.
- **Adding new runtime state** → write under `RUNTIME_DIR / "your_state.json"`.
  Make sure your writer calls `dir_.mkdir(parents=True, exist_ok=True)`.
- **When to create a subdirectory** —
  - **Pure flat for 1–2 files** (e.g. one `*.md` doesn't justify nesting).
  - **Subdir for ≥3 files of the same kind** (e.g. `knowledge_packs/` ←
    multiple packs of identical format).
  - **Subdir for service-exclusive collections** if ≥3 such files exist;
    otherwise stay flat — the cross-service files (`fortune`, `tarot`,
    `embed`) make a service-based split awkward today.
- **Never** mix static and runtime in the same file. If a JSON has both
  shipped defaults and user-edited overrides, split into two files (one in
  `data/`, one in `runtime/`).

## Paths in code

```python
# Static (always present, baked into image):
from core.config import DATA_DIR
load_json(DATA_DIR / "embed.json")

# Mutable (created at first write, volume-mounted):
from core.config import RUNTIME_DIR
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
(RUNTIME_DIR / "log_channels.json").write_text(...)
```

`DATA_DIR` and `RUNTIME_DIR` resolve to `/app/data` and `/app/runtime` inside
containers, and to `<repo>/backend/data` and `<repo>/backend/runtime` when
running outside Docker.

# `backend/data/` — static repo content

This directory holds **read-only configuration baked into every Docker image**
via `COPY data/ ./data/` in each service Dockerfile. Edit a file here, push,
the next deploy ships it.

| Path               | Used by                  | Notes                                    |
| ------------------ | ------------------------ | ---------------------------------------- |
| `chat_filter.json` | twitch AI                | Substring + pinyin block list            |
| `eat.json`         | discord eat cog          | Restaurant list                          |
| `embed.json`       | discord (all cogs)       | Default author/footer chrome             |
| `fortune.json`     | twitch + discord fortune | Lucky text pool                          |
| `free_models.json` | shared AI provider chain | OpenRouter free-tier roster              |
| `games.json`       | discord games cog        | Game catalog                             |
| `giveaway.json`    | discord giveaway cog     | Static config (not active state)         |
| `tarot.json`       | twitch + discord tarot   | 78-card deck                             |
| `packs/<pack>/`    | twitch AI                | Skill-style pack directories (see below) |

## Packs (`packs/`)

Each pack is a **directory** (mirroring Claude Skills layout). The directory
contains a `PACK.md` index and any number of `*.md` entry files, optionally
inside subdirectories for grouping.

### Layout

```text
packs/
├── twitch_culture/
│   ├── PACK.md
│   ├── kappa.md
│   ├── kekw.md
│   └── ...
└── xd_ent/
    ├── PACK.md
    ├── basics.md
    ├── people/
    │   ├── roger.md
    │   └── nl.md
    └── events/
        ├── 2019-roger-hct-championship.md
        └── 2024-xdent-founding.md
```

Convention: use subdirectories to group entries by **role** (`people/`),
**topic** (`events/`), or any other taxonomy that aids maintenance. The
directory name becomes part of the breadcrumb shown to the LLM.

### `PACK.md` — pack metadata (frontmatter only)

```markdown
---
id: twitch_culture
name: Twitch 文化與梗百科
description: Twitch emote 由來、平台黑話與常見梗語解釋
---
```

| Field         | Convention                                                                                                    | Used by                         |
| ------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| `id`          | lowercase `snake_case`, ASCII; usually matches the directory name                                             | code keys, DB `enabled_packs[]` |
| `name`        | **Chinese display name** with proper case for any embedded English (`Twitch 文化與梗百科`, `叉滴娛樂 XD.ent`) | admin Modules page card title   |
| `description` | **Chinese single sentence** summarising what this pack contains                                               | admin Modules page subtitle     |

The body of `PACK.md` (anything after the closing `---`) is **not parsed**;
it's purely documentation for human maintainers. Convention: start with an
`# H1` echoing `name`, plus a short prose intro.

### Entry `*.md` — one knowledge unit per file

```markdown
---
keys: kappa, kappapride, kross
---

Kappa 是 Twitch 最具標誌性的 emote ...
```

| Field  | Convention                                                                                       |
| ------ | ------------------------------------------------------------------------------------------------ |
| `keys` | comma-separated, lowercase. Mix English (`kappa`, `pogchamp`) and CJK (`羅傑`, `叉滴`) as needed |
| body   | Markdown content. Injected verbatim into the system prompt when keys match                       |

Matching rules:

- **ASCII-only key** → word-boundary regex. `w` matches standalone `w` but not inside `kekw`.
- **Key containing any CJK character** → substring match. `羅傑` matches inside `羅傑是誰`.

Key authoring tips:

- **CJK keys: prefer no spaces.** Natural Chinese queries usually have no
  spaces between Han characters, so a key like `叉滴 創辦` (with space) will
  miss the query `叉滴創辦`. Write `叉滴創辦` instead — it matches both
  spaced and unspaced phrasings.
- **List multiple variants** for the same concept (e.g. PogChamp entry has
  `pogchamp, pog, poggers, pogu, komodohype` to catch any phrasing).
- **Keep short keys ASCII-only** so word-boundary protection kicks in
  (`w`, `l`, `gg`); avoid one- or two-character CJK keys that could
  false-positive inside longer text.

Filename conventions:

- **Lowercase kebab-case English** for all entry files and subdirectories
  (`f-in-chat.md`, `people/roger.md`). The filename forms the breadcrumb the
  LLM sees, so keeping it ASCII keeps tokens short and predictable.

Entries without a `keys:` frontmatter line are silently skipped at load time
(this lets you keep draft files or in-pack READMEs without breaking loading).

### LLM injection format

When an entry matches, it is prefixed with a breadcrumb derived from
`pack.name` plus the file path (no extension):

```text
【Twitch 文化與梗百科 / kappa】
Kappa 是 Twitch 最具標誌性的 emote ...

【叉滴娛樂 XD.ent / people / roger】
- 本名：羅晟原
- Twitch ID：roger9527
- ...
```

This is why `name` should be Chinese: it appears verbatim inside the LLM
context, giving the model a clear topical header before the entry body.

### Budget

Each pack has a ~6000-token budget across all entries (estimated as
`total_chars / 4`). Oversize packs are dropped at load time with a warning.

## Sibling: `backend/runtime/`

`backend/runtime/` holds **mutable state** the bot writes at run time
(log channel mappings, in-flight giveaway state, etc.). It is volume-mounted
per environment so each deployment keeps its own state.

| Path                  | Used by              | Notes                     |
| --------------------- | -------------------- | ------------------------- |
| `log_channels.json`   | discord events cog   | Guild → log channel map   |
| `giveaway_state.json` | discord giveaway cog | Active giveaway snapshots |

## Conventions

- **Adding a new static file** → drop the file here, code uses `DATA_DIR /
"your_file.json"`, push. No host-side seeding required on staging/prod.
- **Adding new runtime state** → write under `RUNTIME_DIR / "your_state.json"`.
  Make sure your writer calls `dir_.mkdir(parents=True, exist_ok=True)`.
- **When to create a subdirectory** —
  - **Pure flat for 1–2 files** (e.g. one `*.md` doesn't justify nesting).
  - **Subdir for ≥3 files of the same kind** (e.g. `packs/` ←
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

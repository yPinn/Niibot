# Versioning Convention

## Display Format

```text
v1.3.9 (32f0417)
 │ │ │   └─ short SHA — exact commit reference
 │ │ └─── commit count since last tag — auto-increments with every commit
 │ └───── MINOR — bumped on new features
 └─────── MAJOR — bumped on breaking changes
```

PATCH is **never manually set**. It is generated at build time from `git describe`.

---

## How It Works

The shared deploy workflow (`.github/workflows/_deploy.yml`) runs:

```bash
git describe --tags --always
# e.g. v1.3.0-9-g32f0417
```

And transforms it to the display format:

| `git describe` output | Runtime version    | Note                      |
| --------------------- | ------------------ | ------------------------- |
| `v1.4-9-g32f0417`     | `v1.4.9 (32f0417)` | new-style tag             |
| `v1.4` (exact tag)    | `v1.4.0 (sha)`     | new-style tag             |
| `v1.3.2-9-g32f0417`   | `v1.3.9 (32f0417)` | legacy tag, still handled |
| `v1.3.2` (exact tag)  | `v1.3.0 (sha)`     | legacy tag, still handled |

---

## When to Bump

| Change type                          | Action                                         | Example           |
| ------------------------------------ | ---------------------------------------------- | ----------------- |
| `fix:`, `refactor:`, `chore:`, `ci:` | **Nothing** — commit count bumps automatically | —                 |
| `feat:` — new feature                | Tag new `vMAJOR.MINOR.0`                       | `v1.3.0 → v1.4.0` |
| `feat!:` or `BREAKING CHANGE:`       | Tag new `vMAJOR+1.0.0`                         | `v1.4.0 → v2.0.0` |

---

## Release Process

1. Merge all related PRs into `main`
2. Tag the commit (two segments only, no patch):

   ```bash
   git tag v1.4
   git push origin v1.4
   ```

3. Update `backend/pyproject.toml` `version` to `MAJOR.MINOR`, matching the tag
   (metadata only — not read at runtime). `frontend/package.json` has no
   `version` field and needs no change.

No separate version bump commit is required.

---

## Rules

- **Tags use `vMAJOR.MINOR`** — no patch segment; the runtime patch comes from commit count.
  (Tags before v1.4 used `vMAJOR.MINOR.PATCH` — kept as historical anchors, still handled correctly.)
- **Tag only on `main`**, only when ready to deploy.
- **One tag per release.** Frontend and backend share the same tag.
- **`backend/pyproject.toml` `version` is metadata** — not read at runtime.
  Keep it in sync with the latest tag (two segments, e.g. `1.12`) for tooling
  and human reference. `frontend/package.json` carries no version.

---

## Component Reference

| Component                | Version source at runtime                                        |
| ------------------------ | ---------------------------------------------------------------- |
| API Server               | `APP_VERSION` env var (set from `git describe` in `_deploy.yml`) |
| Twitch Bot               | same                                                             |
| Discord Bot              | same                                                             |
| Frontend                 | `git describe` at Cloudflare Pages build (no `version` field)    |
| `backend/pyproject.toml` | metadata only — not displayed at runtime                         |

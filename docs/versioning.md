# Versioning Convention

## Format

This project uses **Semantic Versioning**: `MAJOR.MINOR.PATCH`

Frontend (`frontend/package.json`) and backend (`backend/pyproject.toml`) share the **same version number** and are bumped together.

---

## When to Bump

| Commit type                           | Version change              | Example         |
| ------------------------------------- | --------------------------- | --------------- |
| `fix:` — bug fixes                    | PATCH +1                    | `1.0.1 → 1.0.2` |
| `feat:` — new features                | MINOR +1, reset PATCH       | `1.0.2 → 1.1.0` |
| `feat!:` or `BREAKING CHANGE:` footer | MAJOR +1, reset MINOR/PATCH | `1.1.0 → 2.0.0` |
| `refactor:`, `chore:`, `docs:`, `ci:` | No version change           | —               |

---

## Release Process

1. Merge all related PRs into `main`
2. Decide the new version according to the table above
3. Update both files to the new version:
   - `frontend/package.json` → `"version": "x.y.z"`
   - `backend/pyproject.toml` → `version = "x.y.z"`
4. Commit the bump:
   ```
   git commit -m "chore: bump version to x.y.z"
   ```
5. Tag the commit:
   ```
   git tag vx.y.z
   git push origin main --tags
   ```
6. Create a GitHub Release from the tag (optional but recommended)

---

## Rules

- **Tag = deployable state.** Only tag commits on `main` that are ready to deploy.
- **One tag per release.** Do not create separate tags for frontend and backend.
- **No skipping.** If two feature PRs land before a release, the version still bumps MINOR once.
- **Breaking changes require a major bump.** Examples: removing an API endpoint, incompatible DB migration, changing auth flow.

---

## Current State

| Component | File                     | Version field      |
| --------- | ------------------------ | ------------------ |
| Frontend  | `frontend/package.json`  | `"version"`        |
| Backend   | `backend/pyproject.toml` | `version`          |
| Git tag   | —                        | `vx.y.z` on `main` |

All three must match after every release commit.

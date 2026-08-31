# Tarot deck assets

Tarot artwork is deployed as immutable frontend static content so the OBS renderer can use
same-origin paths and Discord can use `FRONTEND_URL` absolute URLs.

## Directory contract

```text
decks/<deck-id>/v<positive-integer>/cards/<asset-key>.<format>
```

- `<deck-id>` is lowercase kebab-case and identifies one visual deck.
- A released version directory is immutable. Replace an entire design by adding a new version or
  deck, then change `active_deck` in `backend/data/tarot_decks.json`.
- Each version has an `integrity.json` SHA-256 lock. Never update the lock to overwrite a released
  version; create a new version directory instead.
- Major Arcana keys use `major-NN-english-name` (`major-00-the-fool`).
- Minor Arcana keys use `<suit>-NN-english-name` (`wands-01-ace-of-wands`).
- Minor ranks are Ace `01`, Two–Ten `02`–`10`, Page `11`, Knight `12`, Queen `13`, King `14`.
- Filenames use ASCII lowercase kebab-case. Card ids and meanings remain in
  `backend/data/tarot.json`; filenames never become domain identifiers.

Run `npm run assets:tarot:check` from `frontend/` after adding or changing a deck. The command
requires exactly 78 catalogued images and checks filenames, duplicates, file size, format
signatures, and the immutable version's SHA-256 hashes. Production builds run this check first.

## Current source

`rider-waite-smith-pkt/v1` contains the 78 Pictorial Key to the Tarot illustrations credited to
Arthur Edward Waite and Pamela Colman Smith. Source and provenance are recorded in
`backend/data/tarot_decks.json`.

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repositoryDir = resolve(frontendDir, '..')
const catalogPath = resolve(repositoryDir, 'backend/data/tarot_decks.json')

function fail(message) {
  throw new Error(`[tarot-assets] ${message}`)
}

function matchesFormatSignature(buffer, format) {
  if (format === 'jpg' || format === 'jpeg') {
    return buffer.length >= 3 && buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff
  }
  if (format === 'png') {
    return buffer.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'))
  }
  if (format === 'webp') {
    return (
      buffer.subarray(0, 4).toString('ascii') === 'RIFF' &&
      buffer.subarray(8, 12).toString('ascii') === 'WEBP'
    )
  }
  if (format === 'avif') {
    return buffer.subarray(4, 12).toString('ascii').startsWith('ftypavif')
  }
  return false
}

const catalog = JSON.parse(readFileSync(catalogPath, 'utf8'))
const active = catalog.active_deck
const activeDeck = catalog.decks.find(
  candidate => candidate.id === active.id && candidate.version === active.version
)
if (!activeDeck) fail('active_deck does not reference a registered deck')
if (!Array.isArray(catalog.decks) || catalog.decks.length === 0) {
  fail('catalog must register at least one deck version')
}

function validateDeck(deck) {
  const deckLabel = `${deck.id}/v${deck.version}`
  const expectedFiles = Object.values(deck.cards)
    .map(assetKey => `${assetKey}.${deck.format}`)
    .sort()
  if (expectedFiles.length !== 78 || new Set(expectedFiles).size !== 78) {
    fail(`${deckLabel} must map exactly 78 unique card files`)
  }

  const cardsDir = resolve(
    frontendDir,
    'public/images/tarot/decks',
    deck.id,
    `v${deck.version}`,
    'cards'
  )
  if (!existsSync(cardsDir)) fail(`missing cards directory: ${cardsDir}`)

  const integrityPath = resolve(cardsDir, '..', 'integrity.json')
  if (!existsSync(integrityPath)) fail(`missing integrity lock: ${integrityPath}`)
  const integrity = JSON.parse(readFileSync(integrityPath, 'utf8'))
  if (integrity.schema_version !== 1 || integrity.algorithm !== 'sha256') {
    fail(`${deckLabel} integrity lock must use schema version 1 and SHA-256`)
  }
  const integrityFiles = Object.keys(integrity.files ?? {}).sort()
  if (JSON.stringify(integrityFiles) !== JSON.stringify(expectedFiles)) {
    fail(`${deckLabel} integrity lock contents do not exactly match its catalog`)
  }

  const actualFiles = readdirSync(cardsDir)
    .filter(name => statSync(resolve(cardsDir, name)).isFile())
    .sort()
  if (JSON.stringify(actualFiles) !== JSON.stringify(expectedFiles)) {
    fail(`${deckLabel} card directory contents do not exactly match its catalog`)
  }

  for (const filename of expectedFiles) {
    const file = readFileSync(resolve(cardsDir, filename))
    if (file.length < 1024) fail(`${deckLabel}/${filename} is unexpectedly small`)
    if (!matchesFormatSignature(file, deck.format)) {
      fail(`${deckLabel}/${filename} does not match the declared ${deck.format} format`)
    }
    const actualHash = createHash('sha256').update(file).digest('hex')
    if (integrity.files[filename] !== actualHash) {
      fail(`${deckLabel}/${filename} differs from its immutable version integrity lock`)
    }
  }

  process.stdout.write(
    `[tarot-assets] ${deckLabel}: ${expectedFiles.length} structured card files verified\n`
  )
}

for (const deck of catalog.decks) validateDeck(deck)

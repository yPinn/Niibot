import { readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(import.meta.dirname, '../..')
const fullCss = readFileSync(resolve(import.meta.dirname, 'css/all.css'), 'utf8')
const subsetCss = readFileSync(resolve(import.meta.dirname, 'css/fontawesome.subset.css'), 'utf8')

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return /\.tsx?$/.test(entry.name) ? [path] : []
  })
}

describe('Font Awesome generated subset', () => {
  it('contains every glyph referenced by frontend source', () => {
    const usedTokens = new Set<string>()
    for (const file of sourceFiles(sourceRoot)) {
      for (const match of readFileSync(file, 'utf8').matchAll(/fa-[a-z0-9-]+/g)) {
        usedTokens.add(match[0])
      }
    }

    const missingGlyphs = [...usedTokens]
      .filter(token => fullCss.includes(`.${token}::before`))
      .filter(token => !subsetCss.includes(token))
      .sort()

    expect(missingGlyphs).toEqual([])
  })
})

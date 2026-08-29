/**
 * Client-side mirror of the bot's `render_template` (backend
 * `twitch/utils/event_render.py`). Used only for the live preview — the bot
 * does the real render.
 *
 * 1. `[[ optional ]]` segments collapse when a `$(var)` inside has no value.
 * 2. `$(name)` / `$(@name)` substitute in a single left-to-right pass; unknown
 *    keys stay literal and a substituted value is never re-scanned.
 */
const SEGMENT_RE = /\[\[([\s\S]*?)\]\]/g
const VAR_RE = /\$\((@?\w+)\)/g

export type TemplatePartKind = 'literal' | 'var' | 'dropped'

export interface TemplatePart {
  text: string
  kind: TemplatePartKind
}

/** Split plain text on `$(var)` tokens into literal / var parts. */
function tokenizeVars(text: string, variables: Record<string, string>): TemplatePart[] {
  const parts: TemplatePart[] = []
  let last = 0
  for (const m of text.matchAll(VAR_RE)) {
    const at = m.index ?? 0
    if (at > last) parts.push({ text: text.slice(last, at), kind: 'literal' })
    const name = m[1]
    if (Object.prototype.hasOwnProperty.call(variables, name)) {
      parts.push({ text: variables[name], kind: 'var' })
    } else {
      parts.push({ text: m[0], kind: 'literal' }) // unknown placeholder — left as typed
    }
    last = at + m[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), kind: 'literal' })
  return parts
}

/**
 * Break a template into typed spans for a rich preview. `dropped` parts (a
 * `[[ ]]` segment whose vars aren't all populated) contribute nothing to the
 * rendered string but are kept so the preview can show them struck through.
 */
export function renderTemplateParts(
  template: string,
  variables: Record<string, string>
): TemplatePart[] {
  const parts: TemplatePart[] = []
  let last = 0
  for (const m of template.matchAll(SEGMENT_RE)) {
    const at = m.index ?? 0
    if (at > last) parts.push(...tokenizeVars(template.slice(last, at), variables))
    const seg = m[1]
    const names = [...seg.matchAll(VAR_RE)].map(x => x[1])
    if (names.some(n => !variables[n])) {
      parts.push({ text: seg, kind: 'dropped' })
    } else {
      parts.push(...tokenizeVars(seg, variables))
    }
    last = at + m[0].length
  }
  if (last < template.length) parts.push(...tokenizeVars(template.slice(last), variables))
  return parts
}

export function renderTemplate(template: string, variables: Record<string, string>): string {
  return renderTemplateParts(template, variables)
    .filter(p => p.kind !== 'dropped')
    .map(p => p.text)
    .join('')
}

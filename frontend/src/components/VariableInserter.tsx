import { useState } from 'react'

export interface TemplateVariable {
  var: string
  desc: string
}

export interface VariableInserterProps {
  variables: TemplateVariable[]
  onInsert: (varStr: string) => void
  /** Section label — defaults to "可用變數（點擊插入）". */
  label?: string
}

/**
 * A row of clickable chips that insert template variables into a text field.
 * Chips carry only the token; the hovered / focused chip's description shows in
 * a fixed single-line strip below, so a long description never widens the row
 * and hovering never nudges the layout.
 * Pure presentational — connect `onInsert` to `useInputInsert`'s `insertText`.
 */
export function VariableInserter({
  variables,
  onInsert,
  label = '可用變數（點擊插入）',
}: VariableInserterProps) {
  const [active, setActive] = useState<string | null>(null)
  const clear = (v: string) => setActive(cur => (cur === v ? null : cur))
  const activeDesc = variables.find(v => v.var === active)?.desc

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label text-muted-foreground select-none">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {variables.map(({ var: v }) => (
          <button
            key={v}
            type="button"
            onClick={() => onInsert(v)}
            onMouseEnter={() => setActive(v)}
            onMouseLeave={() => clear(v)}
            onFocus={() => setActive(v)}
            onBlur={() => clear(v)}
            className="cursor-pointer rounded-md border px-2 py-0.5 font-mono text-label text-primary transition-colors hover:bg-accent select-none"
          >
            {v.split(' ')[0]}
          </button>
        ))}
      </div>
      {/* Reserved single-line strip — the row is a fixed height so hovering a
          chip only swaps the text, never nudges the layout. */}
      <div className="border-t pt-1.5">
        <p className="h-4 truncate text-right text-label leading-4 text-muted-foreground">
          {activeDesc}
        </p>
      </div>
    </div>
  )
}

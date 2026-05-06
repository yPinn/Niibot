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
 * Pure presentational — connect `onInsert` to `useInputInsert`'s `insertText`.
 */
export function VariableInserter({
  variables,
  onInsert,
  label = '可用變數（點擊插入）',
}: VariableInserterProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label text-muted-foreground select-none">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {variables.map(({ var: v, desc }) => (
          <button
            key={v}
            type="button"
            onClick={() => onInsert(v)}
            className="inline-flex cursor-pointer items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-label transition-colors hover:bg-accent select-none"
          >
            <span className="text-primary">{v.split(' ')[0]}</span>
            <span className="text-muted-foreground">— {desc}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

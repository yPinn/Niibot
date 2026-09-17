import type { ReactNode } from 'react'

import { Icon } from '@/components/primitives'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import type { TemplatePart } from '@/lib/templateParts'

interface TemplatePartsPreviewProps {
  parts: TemplatePart[]
  limit: number
  label?: string
  legend?: ReactNode
}

/** Shared "highlighted substitution + length counter" preview shell — feed it
 * already-tokenized parts so callers with different template dialects (e.g.
 * check-in's plain $(var)-only renderer vs. events' $(var) + [[ ]] renderer)
 * still get the same look. */
export function TemplatePartsPreview({
  parts,
  limit,
  label = '預覽（以範例值代入）',
  legend,
}: TemplatePartsPreviewProps) {
  const length = parts.reduce((n, p) => (p.kind === 'dropped' ? n : n + p.text.length), 0)
  const over = length > limit
  const empty = length === 0

  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-label text-muted-foreground select-none">
        {label}
        {legend && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex cursor-help">
                <Icon
                  icon="fa-solid fa-circle-info"
                  size="xs"
                  wrapperClassName="text-muted-foreground/50"
                />
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-60 text-label leading-relaxed">
              {legend}
            </TooltipContent>
          </Tooltip>
        )}
      </span>
      <div className="rounded-md border bg-muted/40 px-3 py-2 text-sub wrap-break-word">
        {empty ? (
          <span className="text-muted-foreground">（訊息模板為空）</span>
        ) : (
          parts.map((p, i) =>
            p.kind === 'var' ? (
              <span key={i} className="text-primary">
                {p.text}
              </span>
            ) : p.kind === 'dropped' ? (
              <span key={i} className="text-muted-foreground/40 line-through">
                {p.text}
              </span>
            ) : (
              <span key={i}>{p.text}</span>
            )
          )
        )}
      </div>
      <span className={`text-label ${over ? 'text-status-offline' : 'text-muted-foreground'}`}>
        {length} / {limit}
      </span>
    </div>
  )
}

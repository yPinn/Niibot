import type { EventVariable } from '@/api/events'
import { Icon } from '@/components/primitives'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'

import { renderTemplateParts } from './renderTemplate'

const TWITCH_MESSAGE_LIMIT = 500

interface TemplatePreviewProps {
  template: string
  variables: EventVariable[]
}

export function TemplatePreview({ template, variables }: TemplatePreviewProps) {
  const samples = Object.fromEntries(variables.map(v => [v.name, v.sample]))
  const parts = renderTemplateParts(template, samples)
  const length = parts.reduce((n, p) => (p.kind === 'dropped' ? n : n + p.text.length), 0)
  const over = length > TWITCH_MESSAGE_LIMIT
  const empty = length === 0

  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-label text-muted-foreground select-none">
        預覽（以範例值代入）
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
            <span className="text-primary">紫色</span>為變數代入值；
            <span className="line-through">刪除線</span>片段是{' '}
            <span className="font-mono">[[ ]]</span> 內變數無值、實際不顯示的部分。
          </TooltipContent>
        </Tooltip>
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
        {length} / {TWITCH_MESSAGE_LIMIT}
      </span>
    </div>
  )
}

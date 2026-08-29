import type { EventVariable } from '@/api/events'

import { renderTemplate } from './renderTemplate'

const TWITCH_MESSAGE_LIMIT = 500

interface TemplatePreviewProps {
  template: string
  variables: EventVariable[]
}

export function TemplatePreview({ template, variables }: TemplatePreviewProps) {
  const samples = Object.fromEntries(variables.map(v => [v.name, v.sample]))
  const rendered = renderTemplate(template, samples)
  const over = rendered.length > TWITCH_MESSAGE_LIMIT

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label text-muted-foreground select-none">預覽（以範例值代入）</span>
      <div className="rounded-md border bg-muted/40 px-3 py-2 text-sub break-words">
        {rendered || <span className="text-muted-foreground">（訊息模板為空）</span>}
      </div>
      <span className={`text-label ${over ? 'text-status-offline' : 'text-muted-foreground'}`}>
        {rendered.length} / {TWITCH_MESSAGE_LIMIT}
      </span>
    </div>
  )
}

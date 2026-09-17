import { useMemo } from 'react'

import type { EventVariable } from '@/api/events'
import { TemplatePartsPreview } from '@/components/TemplatePartsPreview'
import { renderTemplateParts } from '@/lib/templateParts'

const TWITCH_MESSAGE_LIMIT = 500

const LEGEND = (
  <>
    <span className="text-primary">紫色</span>為變數代入值；
    <span className="line-through">刪除線</span>片段是 <span className="font-mono">[[ ]]</span>{' '}
    內變數無值、實際不顯示的部分。
  </>
)

interface TemplatePreviewProps {
  template: string
  variables: EventVariable[]
}

export function TemplatePreview({ template, variables }: TemplatePreviewProps) {
  const samples = useMemo(
    () => Object.fromEntries(variables.map(v => [v.name, v.sample])),
    [variables]
  )
  const parts = renderTemplateParts(template, samples)

  return <TemplatePartsPreview parts={parts} limit={TWITCH_MESSAGE_LIMIT} legend={LEGEND} />
}

import { Icon } from '@/components/primitives'
import type { Suggestion, SuggestionTone } from '@/lib/insights-suggestions'
import { cn } from '@/lib/utils'

const TONE_CLASS: Record<SuggestionTone, string> = {
  warning: 'text-status-warning',
  action: 'text-status-info',
  positive: 'text-status-success',
}

export function SuggestedActions({ suggestions }: { suggestions: Suggestion[] }) {
  if (suggestions.length === 0) return null

  return (
    <div className="flex flex-col gap-1.5 shrink-0">
      <p className="text-label text-muted-foreground">建議行動</p>
      <div className="flex flex-col gap-1.5">
        {suggestions.map(s => (
          <div key={s.id} className="flex items-start gap-2 rounded-md border px-2.5 py-2">
            <Icon icon={s.icon} size="sm" wrapperClassName={cn('mt-0.5', TONE_CLASS[s.tone])} />
            <p className="text-sub leading-relaxed">{s.text}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

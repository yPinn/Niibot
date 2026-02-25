import { toast } from 'sonner'

import { Button, Icon, Label } from '@/components/ui'

export interface OverlayUrlBlockProps {
  /** Full overlay URL. When falsy, renders nothing. */
  url: string | undefined
  /** Row label — defaults to "OBS Overlay". */
  label?: string
}

/**
 * Displays an OBS overlay URL with a one-click copy button.
 * Returns null when `url` is empty so callers don't need a guard.
 */
export function OverlayUrlBlock({ url, label = 'OBS Overlay' }: OverlayUrlBlockProps) {
  if (!url) return null

  return (
    <div className="flex items-center gap-3">
      <Label className="shrink-0">{label}</Label>
      <code className="flex-1 truncate rounded bg-muted px-2 py-1 text-label">{url}</code>
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          navigator.clipboard.writeText(url)
          toast.success('已複製')
        }}
      >
        <Icon icon="fa-solid fa-copy" className="text-xs" />
      </Button>
    </div>
  )
}

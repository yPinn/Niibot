import { toast } from 'sonner'

import { Button, Icon, Label } from '@/components/ui'

export interface OverlayUrlBlockProps {
  /** Full overlay URL. When falsy, renders nothing. */
  url: string | undefined
  /** Row label — defaults to "OBS Overlay". */
  label?: string
}

/**
 * Displays an OBS overlay URL. Clicking the URL copies it; the external-link
 * button opens it in a new tab. Returns null when `url` is empty.
 */
export function OverlayUrlBlock({ url, label = 'OBS Overlay' }: OverlayUrlBlockProps) {
  if (!url) return null

  return (
    <div className="flex items-center gap-3">
      <Label className="shrink-0">{label}</Label>
      <code
        className="flex-1 cursor-pointer truncate rounded bg-muted px-2 py-1 text-label transition-colors hover:bg-accent"
        title="點擊複製"
        onClick={() => {
          navigator.clipboard.writeText(url)
          toast.success('已複製')
        }}
      >
        {url}
      </code>
      <Button size="sm" variant="outline" asChild>
        <a href={url} target="_blank" rel="noopener noreferrer">
          <Icon icon="fa-solid fa-arrow-up-right-from-square" className="text-xs" />
        </a>
      </Button>
    </div>
  )
}

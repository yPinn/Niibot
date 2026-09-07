import { useState } from 'react'

import { Icon } from '@/components/primitives'
import { Button, Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { copyToClipboard } from '@/lib/clipboard'

export interface OverlayUrlBlockProps {
  /** Full overlay URL. When falsy, renders nothing. */
  url: string | undefined
  copyLabel?: string
  openLabel?: string
}

/**
 * OBS overlay URL display — mirrors Streamlabs widget URL UX.
 * [icon + label | blurred-URL / hint (click to copy) | eye toggle] | [open btn]
 */
export function OverlayUrlBlock({
  url,
  copyLabel = '點擊以複製 Overlay 連結',
  openLabel = '開啟 OBS Overlay',
}: OverlayUrlBlockProps) {
  const [revealed, setRevealed] = useState(false)

  if (!url) return null

  const copy = () => copyToClipboard(url, '已複製', '複製失敗，請手動選取網址')

  return (
    <div className="flex items-center gap-2">
      {/* URL display area — click to copy */}
      <div
        role="button"
        tabIndex={0}
        className="flex h-9 min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md border bg-background px-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={copy}
        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && copy()}
      >
        <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
          <Icon icon="fa-solid fa-tower-broadcast" className="text-label" />
        </span>
        <div className="h-4 w-px shrink-0 bg-border" />

        {/* URL / hint area */}
        <div className="relative min-w-0 flex-1 overflow-hidden">
          <code
            className={`block select-none truncate text-label transition-all ${revealed ? '' : 'blur-sm'}`}
          >
            {url}
          </code>
          {!revealed && (
            <span className="absolute inset-0 flex items-center justify-center text-label font-medium">
              {copyLabel}
            </span>
          )}
        </div>

        {/* Eye toggle — stops propagation so it doesn't trigger copy */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="shrink-0 select-none text-muted-foreground transition-colors hover:text-foreground"
              onClick={e => {
                e.stopPropagation()
                setRevealed(v => !v)
              }}
            >
              <Icon
                icon={revealed ? 'fa-regular fa-eye-slash' : 'fa-regular fa-eye'}
                className="text-label"
              />
            </button>
          </TooltipTrigger>
          <TooltipContent>{revealed ? '隱藏網址' : '顯示網址'}</TooltipContent>
        </Tooltip>
      </div>

      {/* Open in new tab */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="outline" size="sm" asChild>
            <a href={url} target="_blank" rel="noopener noreferrer">
              <span className="sr-only">{openLabel}</span>
              <Icon icon="fa-solid fa-arrow-up-right-from-square" className="text-label" />
            </a>
          </Button>
        </TooltipTrigger>
        <TooltipContent>在新分頁開啟</TooltipContent>
      </Tooltip>
    </div>
  )
}

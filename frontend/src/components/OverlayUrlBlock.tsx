import { type DragEvent, useState } from 'react'

import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { Icon, Spinner } from '@/components/primitives'
import { Button, Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { copyToClipboard } from '@/lib/clipboard'

/** What OBS should name and size the Browser Source a dropped URL creates. */
export interface ObsDropSource {
  name: string
  width?: number
  height?: number
}

export interface OverlayUrlBlockProps {
  /** Full overlay URL. When falsy, renders nothing. */
  url: string | undefined
  copyLabel?: string
  openLabel?: string
  /** Enables dragging the URL straight into OBS, pre-named and pre-sized. */
  obsSource?: ObsDropSource
  /** Rotates the URL's capability key. Adds a reset button with a confirm step. */
  onRotate?: () => void
  rotating?: boolean
}

/**
 * The URL OBS should open for a dropped link. OBS's drop handler reads
 * `layer-name` / `layer-width` / `layer-height` (and `layer-css`) off the query
 * string to name and size the new Browser Source — nothing else (audio
 * routing, refresh/shutdown behaviour) can be preset this way. The params may
 * stay on the source URL; overlays ignore unknown query params. The `#key=`
 * capability fragment is left untouched.
 */
export function obsDropUrl(url: string, source: ObsDropSource): string {
  const [base, fragment] = url.split('#', 2)
  // encodeURIComponent, not URLSearchParams: the latter writes a space as `+`,
  // which OBS does not decode for layer-name (the source shows "Niibot+Video+Queue").
  const params = [`layer-name=${encodeURIComponent(source.name)}`]
  if (source.width) params.push(`layer-width=${source.width}`)
  if (source.height) params.push(`layer-height=${source.height}`)
  const joined = `${base}${base.includes('?') ? '&' : '?'}${params.join('&')}`
  return fragment !== undefined ? `${joined}#${fragment}` : joined
}

/**
 * OBS overlay URL display — mirrors Streamlabs widget URL UX.
 * [drag handle | blurred URL / hint (click to copy) | eye toggle] [open] [reset]
 */
export function OverlayUrlBlock({
  url,
  copyLabel = '點擊複製 OBS 網址',
  openLabel = '開啟畫面',
  obsSource,
  onRotate,
  rotating = false,
}: OverlayUrlBlockProps) {
  const [revealed, setRevealed] = useState(false)
  const [confirmRotate, setConfirmRotate] = useState(false)

  if (!url) return null

  const copy = () => copyToClipboard(url, '已複製', '複製失敗，請手動選取網址')

  const startDrag = (event: DragEvent<HTMLElement>) => {
    if (!obsSource) return
    const dropUrl = obsDropUrl(url, obsSource)
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData('text/uri-list', dropUrl)
    event.dataTransfer.setData('text/plain', dropUrl)
  }

  return (
    <div className="flex items-center gap-element">
      {/* URL display area — click to copy. The whole surface is one button,
          so nothing in it is selectable except a revealed URL, which stays
          selectable for when the clipboard is blocked. */}
      <div
        role="button"
        tabIndex={0}
        className="flex h-9 min-w-0 flex-1 cursor-pointer select-none items-center gap-element rounded-md border bg-background px-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={copy}
        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && copy()}
      >
        {obsSource ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                draggable
                onDragStart={startDrag}
                onClick={e => e.stopPropagation()}
                aria-label="拖曳到 OBS"
                className="flex shrink-0 cursor-grab items-center gap-1 text-muted-foreground transition-colors hover:text-foreground active:cursor-grabbing"
              >
                <Icon icon="fa-solid fa-grip-vertical" className="text-label" />
                <Icon icon="fa-solid fa-tower-broadcast" className="text-label" />
              </span>
            </TooltipTrigger>
            <TooltipContent>拖曳到 OBS</TooltipContent>
          </Tooltip>
        ) : (
          <span className="flex shrink-0 items-center text-muted-foreground">
            <Icon icon="fa-solid fa-tower-broadcast" className="text-label" />
          </span>
        )}
        <div className="h-4 w-px shrink-0 bg-border" />

        {/* URL / hint area */}
        <div className="relative min-w-0 flex-1 overflow-hidden">
          <code
            className={`block truncate text-label transition-all ${revealed ? 'select-text' : 'blur-sm'}`}
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
              aria-label={revealed ? '隱藏網址' : '顯示網址'}
              className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
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
          <Button variant="outline" size="icon" asChild>
            <a href={url} target="_blank" rel="noopener noreferrer">
              <span className="sr-only">{openLabel}</span>
              <Icon icon="fa-solid fa-arrow-up-right-from-square" className="text-label" />
            </a>
          </Button>
        </TooltipTrigger>
        <TooltipContent>{openLabel}</TooltipContent>
      </Tooltip>

      {onRotate && (
        <>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                aria-label="重設網址"
                disabled={rotating}
                onClick={() => setConfirmRotate(true)}
              >
                {rotating ? <Spinner /> : <Icon icon="fa-solid fa-rotate" className="text-label" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>重設網址</TooltipContent>
          </Tooltip>
          <DeleteConfirmDialog
            open={confirmRotate}
            onOpenChange={setConfirmRotate}
            title="重設網址？"
            description="舊網址會立即失效，請到 OBS 的瀏覽器來源貼上新網址。"
            actionLabel="重設網址"
            onConfirm={() => {
              setConfirmRotate(false)
              onRotate()
            }}
          />
        </>
      )}
    </div>
  )
}

import { memo } from 'react'

import type { Crosshair } from '@/api/crosshairs'
import { Icon } from '@/components/primitives'
import { Button, Card, Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'

import { CrosshairPreview } from './CrosshairPreview'

interface CrosshairCardBaseProps {
  crosshair: Pick<Crosshair, 'name' | 'code' | 'game'>
  onCopy: (code: string) => void
  onCardClick?: () => void
  channelName?: string
  copyCount?: number
  footer?: React.ReactNode
}

export const CrosshairCardBase = memo(function CrosshairCardBase({
  crosshair,
  onCopy,
  onCardClick,
  channelName,
  copyCount,
  footer,
}: CrosshairCardBaseProps) {
  return (
    <Card
      className={cn(
        'overflow-hidden bg-muted py-0!',
        onCardClick && 'cursor-pointer transition-shadow hover:shadow-md'
      )}
      onClick={onCardClick}
    >
      <div className="flex items-center justify-end px-element pt-element sm:justify-start">
        <p
          className="hidden min-w-0 flex-1 truncate px-element text-sub font-medium text-foreground sm:block"
          title={crosshair.name}
        >
          {crosshair.name}
        </p>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={e => {
                if (onCardClick) e.stopPropagation()
                onCopy(crosshair.code)
              }}
            >
              <Icon icon="fa-solid fa-copy" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>複製代碼</TooltipContent>
        </Tooltip>
      </div>
      <div className="flex justify-center py-element">
        <CrosshairPreview game={crosshair.game} code={crosshair.code} size="sm" />
      </div>
      <div className="flex items-center gap-element border-t px-element py-element sm:hidden">
        <Icon icon="fa-solid fa-crosshairs" />
        <p className="min-w-0 truncate text-sub font-medium text-foreground">{crosshair.name}</p>
      </div>
      {(channelName !== undefined || copyCount !== undefined) && (
        <div className="flex items-center justify-between px-element pb-element">
          <span className="min-w-0 flex-1 truncate px-element text-label text-muted-foreground">
            {channelName !== undefined && channelName !== '' ? `@${channelName}` : ''}
          </span>
          {copyCount !== undefined && (
            <span className="flex w-8 shrink-0 select-none items-center justify-center gap-1 text-label text-muted-foreground">
              <Icon icon="fa-solid fa-copy" size="xs" />
              {copyCount}
            </span>
          )}
        </div>
      )}
      {footer}
    </Card>
  )
})

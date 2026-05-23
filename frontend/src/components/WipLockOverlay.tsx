import { Icon } from '@/components/ui'
import { cn } from '@/lib/utils'

interface WipLockOverlayProps {
  className?: string
}

export function WipLockOverlay({ className }: WipLockOverlayProps) {
  return (
    <div className={cn('absolute inset-0 z-modal bg-background/80 backdrop-blur-sm', className)}>
      {/* sticky so the card always stays centered in the visible viewport */}
      <div className="sticky top-0 flex h-svh items-center justify-center p-page">
        <div className="flex flex-col items-center gap-section rounded-xl border bg-card p-card text-center shadow-lg max-w-xs w-full">
          <div className="flex size-14 items-center justify-center rounded-full bg-muted">
            <Icon
              icon="fa-solid fa-screwdriver-wrench"
              wrapperClassName="size-6"
              className="text-xl text-muted-foreground"
            />
          </div>
          <div className="flex flex-col gap-element">
            <p className="text-page-title font-semibold">功能開發中</p>
            <p className="text-sub text-muted-foreground leading-relaxed">
              此頁面正在積極建置，
              <br />
              完成後將立即開放。
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

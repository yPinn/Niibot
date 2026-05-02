import { Icon } from '@/components/ui'
import { cn } from '@/lib/utils'

interface AffiliateLockOverlayProps {
  message: string
  className?: string
}

export function AffiliateLockOverlay({ message, className }: AffiliateLockOverlayProps) {
  return (
    <div
      className={cn(
        'absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-background/80 backdrop-blur-sm',
        className
      )}
    >
      <Icon
        icon="fa-solid fa-lock"
        className="text-5xl text-muted-foreground"
        wrapperClassName="size-16"
      />
      <span className="text-sub text-muted-foreground">{message}</span>
    </div>
  )
}

import { cn } from '@/lib/utils'

interface IconProps {
  icon: string
  className?: string
  wrapperClassName?: string
}

export function Icon({ icon, className, wrapperClassName }: IconProps) {
  return (
    <div className={cn('flex size-4 items-center justify-center', wrapperClassName)}>
      <i className={cn(icon, className)} />
    </div>
  )
}

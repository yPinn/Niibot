import { cn } from '@/lib/utils'

interface IconProps {
  icon: string
  className?: string
  wrapperClassName?: string
  /**
   * 是否為固定寬度 icon (適用於 FA6)
   */
  fixedWidth?: boolean
}

/**
 * Icon 組件 - 支援 Font Awesome 6 和 Bootstrap Icons
 *
 * @example
 * // Font Awesome 6
 * <Icon icon="fa-solid fa-home" />
 * <Icon icon="fa-brands fa-twitch" />
 *
 * // Bootstrap Icons
 * <Icon icon="bi bi-house" />
 */
export function Icon({ icon, className, wrapperClassName, fixedWidth = false }: IconProps) {
  // 檢測是否為 Font Awesome icon
  const isFontAwesome =
    icon.startsWith('fa-') ||
    icon.includes('fa-solid') ||
    icon.includes('fa-brands') ||
    icon.includes('fa-regular') ||
    icon.includes('fa-light')

  // 自動添加 fa-fw (固定寬度) class
  const iconClasses = cn(
    icon,
    {
      'fa-fw': isFontAwesome && fixedWidth,
    },
    className
  )

  return (
    <div className={cn('flex size-4 items-center justify-center', wrapperClassName)}>
      <i className={iconClasses} />
    </div>
  )
}

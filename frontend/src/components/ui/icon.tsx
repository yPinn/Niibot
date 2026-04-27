import { cn } from '@/lib/utils'

/**
 * 尺寸對應 iOS SF Symbols 語義規範：
 *
 * box  — wrapper 的 layout 佔位（size-*）
 * font — 明確設定在 wrapper 上的 font-size，讓 <i> 繼承，
 *         不受父層 typography 影響。
 *
 * xs  10px  微型狀態點、radio 指示
 * sm  14px  按鈕 icon、badge（= text-sub）
 * md  16px  預設，inline 文字 icon（= text-content）
 * lg  20px  列表項目、功能卡片 icon（= text-section-title）
 * xl  24px  區塊標題、nav icon（= text-page-title level）
 * 2xl 32px  Hero、空狀態插圖
 */
const SIZES = {
  xs: { box: 'size-2.5', font: 'text-[10px]' },
  '2xs': { box: 'size-3', font: 'text-xs' },
  sm: { box: 'size-3.5', font: 'text-sm' },
  md: { box: 'size-4', font: 'text-base' },
  lg: { box: 'size-5', font: 'text-xl' },
  xl: { box: 'size-6', font: 'text-2xl' },
  '2xl': { box: 'size-8', font: 'text-[32px]' },
} as const

type IconSize = keyof typeof SIZES

interface IconProps {
  icon: string
  /** 語義尺寸，同時控制 wrapper 佔位與 icon font-size。 */
  size?: IconSize
  className?: string
  /**
   * 覆寫 wrapper 屬性（color、border-radius 等）。
   * 外部間距請交由父層 gap 控制，勿在此設定 margin。
   */
  wrapperClassName?: string
  fixedWidth?: boolean
}

export function Icon({
  icon,
  size = 'md',
  className,
  wrapperClassName,
  fixedWidth = false,
}: IconProps) {
  const isFontAwesome =
    icon.startsWith('fa-') ||
    icon.includes('fa-solid') ||
    icon.includes('fa-brands') ||
    icon.includes('fa-regular') ||
    icon.includes('fa-light')

  const iconClasses = cn(icon, { 'fa-fw': isFontAwesome && fixedWidth }, className)

  return (
    <div
      data-slot="icon"
      className={cn(
        'flex shrink-0 items-center justify-center leading-none',
        SIZES[size].box,
        SIZES[size].font,
        wrapperClassName
      )}
    >
      <i className={iconClasses} />
    </div>
  )
}

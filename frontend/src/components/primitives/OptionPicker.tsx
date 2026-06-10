import { Label } from '@/components/ui'
import { cn } from '@/lib/utils'

interface OptionPickerProps<T extends string | number> {
  options: { value: T; label: string; desc?: string }[]
  value: T
  onChange: (v: T) => void
  /** When provided, renders a Label header above the button group. */
  label?: string
  disabled?: boolean
  className?: string
  labelClassName?: string
}

export function OptionPicker<T extends string | number>({
  options,
  value,
  onChange,
  label,
  disabled,
  className,
  labelClassName,
}: OptionPickerProps<T>) {
  const buttons = (
    <div className="flex flex-wrap gap-2">
      {options.map(opt => (
        <button
          key={String(opt.value)}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.value)}
          className={cn(
            'select-none rounded-md border text-sub font-medium transition-colors disabled:opacity-50',
            opt.desc ? 'flex flex-col px-4 py-2 text-left min-w-30' : 'px-3 py-1.5',
            value === opt.value ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-accent'
          )}
        >
          <span>{opt.label}</span>
          {opt.desc && (
            <span className="mt-0.5 text-label font-normal text-muted-foreground">{opt.desc}</span>
          )}
        </button>
      ))}
    </div>
  )

  if (label === undefined) return buttons

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <Label className={labelClassName}>{label}</Label>
      {buttons}
    </div>
  )
}

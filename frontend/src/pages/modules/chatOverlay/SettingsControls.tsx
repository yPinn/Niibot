import { Label } from '@/components/ui'

export function StepSlider<T extends string | number>({
  label,
  steps,
  value,
  onChange,
  unit,
}: {
  label: string
  steps: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  unit?: string
}) {
  const idx = Math.max(
    0,
    steps.findIndex(s => s.value === value)
  )
  const current = steps[idx]
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        <span className="font-mono text-label text-muted-foreground">
          {current.label}
          {unit ? ` · ${current.value}${unit}` : ''}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={steps.length - 1}
        step={1}
        value={idx}
        onChange={e => onChange(steps[+e.target.value].value)}
        style={{ accentColor: 'var(--color-primary)' }}
        className="w-full cursor-pointer"
      />
      <div className="flex justify-between">
        {steps.map((s, i) => (
          <span
            key={i}
            onClick={() => onChange(s.value)}
            className={`cursor-pointer select-none text-[10px] leading-none transition-colors ${
              i === idx
                ? 'text-primary font-semibold'
                : 'text-muted-foreground/50 hover:text-muted-foreground'
            }`}
          >
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}

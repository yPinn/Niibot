import { useId } from 'react'

import { Icon } from '@/components/primitives'
import { Input, Label } from '@/components/ui'

interface SecretInputProps {
  label: string
  value: string
  onChange: (value: string) => void
  /** Reveal state is controlled by the parent so several fields can share one toggle. */
  revealed: boolean
  onToggleReveal: () => void
  id?: string
  placeholder?: string
  disabled?: boolean
}

/** Masked text input with a reveal toggle — for API keys, hashes, and the like. */
export function SecretInput({
  label,
  value,
  onChange,
  revealed,
  onToggleReveal,
  id,
  placeholder,
  disabled,
}: SecretInputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId

  return (
    <div className="flex flex-col gap-1">
      <Label className="text-label text-muted-foreground" htmlFor={inputId}>
        {label}
      </Label>
      <div className="relative">
        <Input
          id={inputId}
          type={revealed ? 'text' : 'password'}
          value={value}
          disabled={disabled}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-8 text-sub pr-8"
        />
        <button
          type="button"
          aria-label={revealed ? '隱藏金鑰' : '顯示金鑰'}
          onClick={onToggleReveal}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        >
          <Icon
            icon={revealed ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye'}
            wrapperClassName="size-3.5"
          />
        </button>
      </div>
    </div>
  )
}

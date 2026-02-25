import { useEffect, useRef } from 'react'

export interface UseInputInsertReturn {
  /** Attach this ref to the <Input> or <textarea> element. */
  inputRef: React.RefObject<HTMLInputElement | null>
  /** Inserts `text` at the current cursor position (or appends if no ref). */
  insertText: (text: string) => void
}

/**
 * Manages cursor-aware text insertion for template variable buttons.
 *
 * Usage:
 *   const { inputRef, insertText } = useInputInsert(formValue, setFormValue)
 *   <Input ref={inputRef} value={formValue} onChange={e => setFormValue(e.target.value)} />
 *   <VariableInserter onInsert={insertText} ... />
 */
export function useInputInsert(
  value: string,
  onChange: (newValue: string) => void
): UseInputInsertReturn {
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Keep latest value + onChange in refs so insertText never captures a stale closure.
  const valueRef = useRef(value)
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    valueRef.current = value
    onChangeRef.current = onChange
  })

  const insertText = (text: string) => {
    const input = inputRef.current
    const currentValue = valueRef.current
    const handleChange = onChangeRef.current

    if (!input) {
      handleChange(currentValue + text)
      return
    }

    const start = input.selectionStart ?? currentValue.length
    const end = input.selectionEnd ?? currentValue.length
    const newValue = currentValue.slice(0, start) + text + currentValue.slice(end)
    handleChange(newValue)

    requestAnimationFrame(() => {
      input.focus()
      const pos = start + text.length
      input.setSelectionRange(pos, pos)
    })
  }

  return { inputRef, insertText }
}

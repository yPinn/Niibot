import { useEffect, useRef } from 'react'

export interface UseInputInsertReturn<
  T extends HTMLInputElement | HTMLTextAreaElement = HTMLInputElement | HTMLTextAreaElement,
> {
  /** Attach this ref to the <Input> or <Textarea> element. */
  inputRef: React.RefObject<T | null>
  /** Inserts `text` at the current cursor position (or appends if no ref). */
  insertText: (text: string) => void
}

export function useInputInsert<
  T extends HTMLInputElement | HTMLTextAreaElement = HTMLInputElement | HTMLTextAreaElement,
>(value: string, onChange: (newValue: string) => void): UseInputInsertReturn<T> {
  const inputRef = useRef<T>(null)

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

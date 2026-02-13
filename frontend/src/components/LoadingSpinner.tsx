import { useEffect, useState } from 'react'

import { Spinner } from '@/components/ui'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  text?: string
  fullScreen?: boolean
  delay?: number
}

export function LoadingSpinner({
  size = 'md',
  text,
  fullScreen = false,
  delay = 200,
}: LoadingSpinnerProps) {
  const [show, setShow] = useState(delay === 0)

  useEffect(() => {
    if (delay === 0) return

    const timer = setTimeout(() => {
      setShow(true)
    }, delay)

    return () => clearTimeout(timer)
  }, [delay])

  if (!show) {
    return null
  }

  const sizeClasses = {
    sm: 'size-4',
    md: 'size-8',
    lg: 'size-12',
  }

  const spinner = (
    <div className="flex flex-col items-center justify-center gap-2">
      <Spinner className={`${sizeClasses[size]} text-primary`} />
      {text && <p className="text-sm text-muted-foreground">{text}</p>}
    </div>
  )

  if (fullScreen) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm animate-fadeIn animate-duration-200">
        {spinner}
      </div>
    )
  }

  return spinner
}

import { useEffect } from 'react'

function setTemporaryMeta(name: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
  const created = !element
  const previousContent = element?.getAttribute('content') ?? null

  if (!element) {
    element = document.createElement('meta')
    element.name = name
    document.head.appendChild(element)
  }
  element.content = content

  return () => {
    if (created) {
      element.remove()
    } else if (previousContent === null) {
      element.removeAttribute('content')
    } else {
      element.content = previousContent
    }
  }
}

/** Adds browser-level defense in depth for public pages that carry one-time capabilities. */
export function useSensitivePageMetadata() {
  useEffect(() => {
    const restoreRobots = setTemporaryMeta('robots', 'noindex, nofollow')
    const restoreReferrer = setTemporaryMeta('referrer', 'no-referrer')
    return () => {
      restoreRobots()
      restoreReferrer()
    }
  }, [])
}

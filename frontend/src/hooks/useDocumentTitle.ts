import { useEffect } from 'react'

const SUFFIX = ' | Niibot'

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title.endsWith(SUFFIX) ? title : title + SUFFIX
    return () => {
      document.title = 'Niibot'
    }
  }, [title])
}

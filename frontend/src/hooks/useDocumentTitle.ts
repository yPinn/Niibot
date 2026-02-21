import { useEffect } from 'react'

const SITE = 'Niibot'
const SUFFIX = ` | ${SITE}`

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title.endsWith(SUFFIX) ? title : title + SUFFIX
    return () => {
      document.title = SITE
    }
  }, [title])
}

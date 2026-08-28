import { apiCache } from '@/lib/apiCache'
import { reportSilent } from '@/lib/clientErrorReporter'

import { API_ENDPOINTS, apiFetch } from './config'
import { parseApiError } from './errors'

export interface GithubRelease {
  id: number
  tag_name: string
  name: string | null
  body: string | null
  published_at: string
  prerelease: boolean
  draft: boolean
}

export async function getReleases(): Promise<GithubRelease[] | null> {
  return apiCache.fetch(
    'releases',
    async () => {
      try {
        const response = await apiFetch(API_ENDPOINTS.releases.list, {
          credentials: 'include',
        })
        if (!response.ok) {
          reportSilent(await parseApiError(response, '載入版本紀錄失敗'))
          return null
        }
        return (await response.json()) as GithubRelease[]
      } catch (error) {
        if (import.meta.env.DEV) console.error('Failed to get releases:', error)
        reportSilent(error)
        return null
      }
    },
    { ttl: 5 * 60 * 1000 }
  )
}

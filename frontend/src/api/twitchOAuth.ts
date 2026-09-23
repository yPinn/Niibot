import { API_ENDPOINTS, assertTrustedOAuthUrl } from './config'
import { ApiError, NETWORK_ERROR, parseApiJsonResponse } from './errors'

interface TwitchOAuthResponse {
  oauth_url: unknown
}

export async function getTwitchOAuthUrl(): Promise<string> {
  const fallback = '登入服務暫時無法使用，請稍後再試'
  let response: Response
  try {
    response = await fetch(API_ENDPOINTS.auth.twitchOAuth)
  } catch {
    throw new ApiError({
      message: '網路連線出了問題，請檢查後再試',
      status: 0,
      code: NETWORK_ERROR,
    })
  }

  const data = await parseApiJsonResponse<TwitchOAuthResponse>(response, fallback)
  return assertTrustedOAuthUrl(data.oauth_url, 'twitch')
}

// Note: Uses raw fetch() intentionally — this is the login initiation endpoint.
// Using apiFetch() would trigger the 401 redirect loop on the login page itself.

export async function openTwitchOAuth(): Promise<void> {
  if (!oauthStartPromise) {
    oauthStartPromise = getTwitchOAuthUrl()
      .then(oauthUrl => {
        window.location.href = oauthUrl
      })
      .finally(() => {
        oauthStartPromise = null
      })
  }
  return oauthStartPromise
}

let oauthStartPromise: Promise<void> | null = null

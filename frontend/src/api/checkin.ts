import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface CheckinSettings {
  channel_id: string
  timezone: string
  success_template: string
  duplicate_template: string
  created_at: string | null
  updated_at: string | null
}

export interface CheckinSettingsUpdate {
  timezone: string
  success_template: string
  duplicate_template: string
}

export function getCheckinSettings(): Promise<CheckinSettings> {
  return apiJson(
    API_ENDPOINTS.checkin.settings,
    { credentials: 'include' },
    { fallback: '載入簽到設定失敗' }
  )
}

export function updateCheckinSettings(update: CheckinSettingsUpdate): Promise<CheckinSettings> {
  return apiJson(
    API_ENDPOINTS.checkin.settings,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-settings',
      },
      body: JSON.stringify(update),
    },
    { fallback: '儲存簽到設定失敗' }
  )
}

import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface CheckinSettings {
  channel_id: string
  timezone: string
  success_template: string
  duplicate_template: string
  reply_delay_seconds: number
  created_at: string | null
  updated_at: string | null
}

export interface CheckinSettingsUpdate {
  timezone: string
  success_template: string
  duplicate_template: string
  reply_delay_seconds: number
}

export interface CheckinLeaderboardEntry {
  rank: number
  user_id: string
  username: string
  display_name: string | null
  total_days: number
  last_checkin_date: string
}

export function getCheckinSettings(): Promise<CheckinSettings> {
  return apiJson(
    API_ENDPOINTS.checkin.settings,
    { credentials: 'include' },
    { fallback: '載入簽到設定失敗' }
  )
}

export function getCheckinLeaderboard(): Promise<CheckinLeaderboardEntry[]> {
  return apiJson(
    API_ENDPOINTS.checkin.leaderboard,
    { credentials: 'include' },
    { fallback: '載入簽到排行榜失敗' }
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

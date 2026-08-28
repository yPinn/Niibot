import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export type DonationPlatform = 'ecpay' | 'opay' | 'paypal' | 'newebpay'

export interface PaymentConfigResponse {
  platform: DonationPlatform
  merchant_id: string
  has_hash: boolean
  min_amount: number
  media_share_enabled: boolean
  enabled: boolean
  updated_at: string | null
}

export interface PaymentConfigUpsert {
  merchant_id: string
  hash_key?: string
  hash_iv?: string
  min_amount?: number
  media_share_enabled?: boolean
  enabled?: boolean
}

export interface PublicPlatformInfo {
  platform: DonationPlatform
  min_amount: number
  media_share_enabled: boolean
}

export interface PublicDonateInfo {
  username: string
  display_name: string | null
  platforms: PublicPlatformInfo[]
}

export interface CheckoutRequest {
  platform: DonationPlatform
  amount: number
  message?: string
  youtube_url?: string
  return_url?: string
}

export interface CheckoutResponse {
  gateway_url: string
  form_params: Record<string, string>
}

export function getPaymentConfigs(): Promise<PaymentConfigResponse[]> {
  return apiJson(
    API_ENDPOINTS.paymentConfigs.list,
    { credentials: 'include' },
    { fallback: '載入贊助設定失敗' }
  )
}

export function upsertPaymentConfig(
  platform: DonationPlatform,
  data: PaymentConfigUpsert
): Promise<PaymentConfigResponse> {
  return apiJson(
    API_ENDPOINTS.paymentConfigs.upsert(platform),
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '儲存贊助設定失敗' }
  )
}

export function deletePaymentConfig(platform: DonationPlatform): Promise<void> {
  return apiJson(
    API_ENDPOINTS.paymentConfigs.delete(platform),
    { method: 'DELETE', credentials: 'include' },
    { fallback: '刪除贊助設定失敗' }
  )
}

export function getPublicDonateInfo(username: string): Promise<PublicDonateInfo> {
  return apiJson(API_ENDPOINTS.donate.public(username), undefined, {
    fallback: '載入贊助資訊失敗',
  })
}

export function createCheckout(username: string, data: CheckoutRequest): Promise<CheckoutResponse> {
  return apiJson(
    API_ENDPOINTS.donate.checkout(username),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
    { fallback: '建立結帳失敗' }
  )
}

export const PLATFORM_LABELS: Record<DonationPlatform, string> = {
  ecpay: '綠界 ECPay',
  opay: '歐付寶 OPay',
  paypal: 'PayPal',
  newebpay: '藍新金流 NewebPay',
}

export const PLATFORM_COLORS: Record<DonationPlatform, string> = {
  ecpay: '#00a651',
  opay: '#ff6600',
  paypal: '#003087',
  newebpay: '#0070c0',
}

export const NEEDS_HASH: Record<DonationPlatform, boolean> = {
  ecpay: true,
  opay: true,
  paypal: false,
  newebpay: true,
}

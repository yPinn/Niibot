import { API_ENDPOINTS, apiFetch } from './config'

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

export async function getPaymentConfigs(): Promise<PaymentConfigResponse[]> {
  const res = await apiFetch(API_ENDPOINTS.paymentConfigs.list, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error('Failed to fetch payment configs')
  return res.json()
}

export async function upsertPaymentConfig(
  platform: DonationPlatform,
  data: PaymentConfigUpsert
): Promise<PaymentConfigResponse> {
  const res = await apiFetch(API_ENDPOINTS.paymentConfigs.upsert(platform), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || 'Failed to save payment config')
  }
  return res.json()
}

export async function deletePaymentConfig(platform: DonationPlatform): Promise<void> {
  const res = await apiFetch(API_ENDPOINTS.paymentConfigs.delete(platform), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || 'Failed to delete payment config')
  }
}

export async function getPublicDonateInfo(username: string): Promise<PublicDonateInfo> {
  const res = await apiFetch(API_ENDPOINTS.donate.public(username))
  if (res.status === 404) throw new Error('Streamer not found')
  if (!res.ok) throw new Error('Failed to load donation info')
  return res.json()
}

export async function createCheckout(
  username: string,
  data: CheckoutRequest
): Promise<CheckoutResponse> {
  const res = await apiFetch(API_ENDPOINTS.donate.checkout(username), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || 'Failed to create checkout')
  }
  return res.json()
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

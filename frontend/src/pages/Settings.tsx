import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { getLinkedAccounts, type LinkedAccount, openOAuthLink, unlinkAccount } from '@/api'
import {
  deletePaymentConfig,
  type DonationPlatform,
  getPaymentConfigs,
  NEEDS_HASH,
  PLATFORM_LABELS,
  type PaymentConfigResponse,
  upsertPaymentConfig,
} from '@/api/donation'
import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Input,
  Label,
  Separator,
  Skeleton,
  Switch,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const ERROR_MESSAGES: Record<string, string> = {
  already_linked: '此帳號已綁定至其他使用者',
  platform_already_linked: '你已經綁定了此平台的帳號',
  invalid_state: '連結狀態無效，請重試',
  not_authenticated: '請先登入再連結帳號',
  session_mismatch: '登入狀態已變更，請重新操作',
}

const PLATFORM_CONFIG = {
  twitch: { icon: 'fa-brands fa-twitch', label: 'Twitch', color: 'text-purple-500' },
  discord: { icon: 'fa-brands fa-discord', label: 'Discord', color: 'text-blue-500' },
} as const

const ALL_PLATFORMS: DonationPlatform[] = ['ecpay', 'opay', 'newebpay', 'paypal']

interface PaymentFormState {
  merchant_id: string
  hash_key: string
  hash_iv: string
  min_amount: string
  media_share_enabled: boolean
  enabled: boolean
}

function emptyForm(minAmount = 30): PaymentFormState {
  return {
    merchant_id: '',
    hash_key: '',
    hash_iv: '',
    min_amount: String(minAmount),
    media_share_enabled: false,
    enabled: true,
  }
}

function configToForm(c: PaymentConfigResponse): PaymentFormState {
  return {
    merchant_id: c.merchant_id,
    hash_key: '',
    hash_iv: '',
    min_amount: String(c.min_amount),
    media_share_enabled: c.media_share_enabled,
    enabled: c.enabled,
  }
}

export default function Settings() {
  useDocumentTitle('Settings')
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [accounts, setAccounts] = useState<LinkedAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [unlinking, setUnlinking] = useState<string | null>(null)

  // Payment config state
  const [paymentConfigs, setPaymentConfigs] = useState<PaymentConfigResponse[]>([])
  const [paymentLoading, setPaymentLoading] = useState(true)
  const [paymentForms, setPaymentForms] = useState<Record<DonationPlatform, PaymentFormState>>({
    ecpay: emptyForm(),
    opay: emptyForm(),
    paypal: emptyForm(),
    newebpay: emptyForm(),
  })
  const [paymentSaving, setPaymentSaving] = useState<DonationPlatform | null>(null)
  const [paymentDeleting, setPaymentDeleting] = useState<DonationPlatform | null>(null)

  const fetchAccounts = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getLinkedAccounts()
      setAccounts(data)
    } catch {
      toast.error('無法載入已連結帳號')
    } finally {
      setLoading(false)
    }
  }, [])

  // Process OAuth redirect params once on mount — runs before searchParams changes
  useEffect(() => {
    const linked = searchParams.get('linked')
    const error = searchParams.get('error')

    if (linked) {
      toast.success('帳號連結成功', {
        description: `已連結 ${PLATFORM_CONFIG[linked as keyof typeof PLATFORM_CONFIG]?.label ?? linked} 帳號`,
      })
      setSearchParams({}, { replace: true })
    }

    if (error) {
      toast.error('帳號連結失敗', {
        description: ERROR_MESSAGES[error] || `連結失敗 (${error})`,
      })
      setSearchParams({}, { replace: true })
    }
    // Intentionally runs only once on mount to process OAuth redirect params.
    // setSearchParams is stable and searchParams is read synchronously.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Fetch accounts on mount; fetchAccounts is stable (useCallback with [])
  useEffect(() => {
    fetchAccounts()
  }, [fetchAccounts])

  const handleUnlink = async (platform: 'twitch' | 'discord') => {
    try {
      setUnlinking(platform)
      await unlinkAccount(platform)
      toast.success(`已取消連結 ${PLATFORM_CONFIG[platform].label} 帳號`)
      await fetchAccounts()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '請稍後再試'
      toast.error('取消連結失敗', { description: message })
    } finally {
      setUnlinking(null)
    }
  }

  const handleLink = async (platform: 'twitch' | 'discord') => {
    try {
      await openOAuthLink(platform)
    } catch {
      toast.error(`無法開啟 ${PLATFORM_CONFIG[platform].label} 登入`)
    }
  }

  const hasPlatform = (platform: string) => accounts.some(a => a.platform === platform)

  const fetchPaymentConfigs = useCallback(async () => {
    try {
      setPaymentLoading(true)
      const configs = await getPaymentConfigs()
      setPaymentConfigs(configs)
      setPaymentForms(prev => {
        const updated = { ...prev }
        for (const c of configs) {
          updated[c.platform as DonationPlatform] = configToForm(c)
        }
        return updated
      })
    } catch {
      toast.error('無法載入金流設定')
    } finally {
      setPaymentLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPaymentConfigs()
  }, [fetchPaymentConfigs])

  const handleSavePaymentConfig = async (platform: DonationPlatform) => {
    const form = paymentForms[platform]
    setPaymentSaving(platform)
    try {
      await upsertPaymentConfig(platform, {
        merchant_id: form.merchant_id,
        hash_key: form.hash_key || undefined,
        hash_iv: form.hash_iv || undefined,
        min_amount: parseInt(form.min_amount, 10) || 30,
        media_share_enabled: form.media_share_enabled,
        enabled: form.enabled,
      })
      toast.success(`已儲存 ${PLATFORM_LABELS[platform]} 設定`)
      await fetchPaymentConfigs()
    } catch (err) {
      toast.error('儲存失敗', { description: err instanceof Error ? err.message : '請稍後再試' })
    } finally {
      setPaymentSaving(null)
    }
  }

  const handleDeletePaymentConfig = async (platform: DonationPlatform) => {
    setPaymentDeleting(platform)
    try {
      await deletePaymentConfig(platform)
      toast.success(`已刪除 ${PLATFORM_LABELS[platform]} 設定`)
      setPaymentForms(prev => ({ ...prev, [platform]: emptyForm() }))
      await fetchPaymentConfigs()
    } catch (err) {
      toast.error('刪除失敗', { description: err instanceof Error ? err.message : '請稍後再試' })
    } finally {
      setPaymentDeleting(null)
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
      <PageHeader title="Settings" description="管理帳號設定與偏好" />

      <Card>
        <CardHeader>
          <CardTitle>已連結帳號</CardTitle>
          <CardDescription>連結你的 Twitch 與 Discord 帳號，跨平台使用所有功能</CardDescription>
        </CardHeader>
        <CardContent className="space-y-section">
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            <>
              {accounts.length > 0 && (
                <div className="space-y-3">
                  {accounts.map(account => {
                    const config = PLATFORM_CONFIG[account.platform]
                    const isCurrent = user?.platform === account.platform
                    const isLast = accounts.length <= 1
                    const canUnlink = !isCurrent && !isLast

                    return (
                      <div
                        key={account.platform}
                        className="flex items-center justify-between rounded-lg border p-card"
                      >
                        <div className="flex items-center gap-3">
                          <Icon
                            icon={config.icon}
                            className={`text-section-title ${config.color}`}
                            wrapperClassName="size-8"
                          />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-medium">{account.username}</span>
                              {isCurrent && (
                                <Badge variant="secondary" className="text-label">
                                  目前工作階段
                                </Badge>
                              )}
                            </div>
                            <span className="text-sub text-muted-foreground">{config.label}</span>
                          </div>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleUnlink(account.platform)}
                          disabled={!canUnlink || unlinking === account.platform}
                        >
                          {unlinking === account.platform ? (
                            <Icon
                              icon="fa-solid fa-spinner"
                              className="animate-spin"
                              wrapperClassName=""
                            />
                          ) : (
                            <Icon icon="fa-solid fa-link-slash" wrapperClassName="" />
                          )}
                          取消連結
                        </Button>
                      </div>
                    )
                  })}
                </div>
              )}

              <Separator />

              <div className="space-y-3">
                <h3 className="text-sub font-medium text-muted-foreground">連結其他帳號</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(
                    Object.entries(PLATFORM_CONFIG) as [
                      keyof typeof PLATFORM_CONFIG,
                      (typeof PLATFORM_CONFIG)[keyof typeof PLATFORM_CONFIG],
                    ][]
                  ).map(([platform, config]) => {
                    const linked = hasPlatform(platform)
                    return (
                      <Button
                        key={platform}
                        variant="outline"
                        className="justify-start"
                        onClick={() => handleLink(platform)}
                        disabled={linked}
                      >
                        <Icon icon={config.icon} className={config.color} wrapperClassName="" />
                        {linked ? `${config.label} 已連結` : `連結 ${config.label} 帳號`}
                      </Button>
                    )
                  })}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>斗內金流設定</CardTitle>
          <CardDescription>
            設定你的 ECPay / OPay / PayPal 收款帳號，讓觀眾可以透過 /donate/{user?.name} 斗內支持你
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-section">
          {paymentLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : (
            <div className="space-y-4">
              {ALL_PLATFORMS.map(platform => {
                const form = paymentForms[platform]
                const existing = paymentConfigs.find(c => c.platform === platform)
                const needsHash = NEEDS_HASH[platform]
                const label = PLATFORM_LABELS[platform]
                const isSaving = paymentSaving === platform
                const isDeleting = paymentDeleting === platform

                return (
                  <div key={platform} className="rounded-lg border p-card space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{label}</span>
                      {existing && <Badge variant="secondary">已設定</Badge>}
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor={`${platform}-merchant`}>
                        {platform === 'paypal' ? 'PayPal.me URL' : '商店代號 (MerchantID)'}
                      </Label>
                      <Input
                        id={`${platform}-merchant`}
                        value={form.merchant_id}
                        onChange={e =>
                          setPaymentForms(prev => ({
                            ...prev,
                            [platform]: { ...prev[platform], merchant_id: e.target.value },
                          }))
                        }
                        placeholder={
                          platform === 'paypal' ? 'https://paypal.me/yourname' : '商店代號'
                        }
                      />
                    </div>

                    {needsHash && (
                      <>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1.5">
                            <Label htmlFor={`${platform}-hashkey`}>
                              HashKey{existing?.has_hash ? ' (留空保持不變)' : ''}
                            </Label>
                            <Input
                              id={`${platform}-hashkey`}
                              type="password"
                              value={form.hash_key}
                              onChange={e =>
                                setPaymentForms(prev => ({
                                  ...prev,
                                  [platform]: { ...prev[platform], hash_key: e.target.value },
                                }))
                              }
                              placeholder={existing?.has_hash ? '••••••••' : 'HashKey'}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor={`${platform}-hashiv`}>
                              HashIV{existing?.has_hash ? ' (留空保持不變)' : ''}
                            </Label>
                            <Input
                              id={`${platform}-hashiv`}
                              type="password"
                              value={form.hash_iv}
                              onChange={e =>
                                setPaymentForms(prev => ({
                                  ...prev,
                                  [platform]: { ...prev[platform], hash_iv: e.target.value },
                                }))
                              }
                              placeholder={existing?.has_hash ? '••••••••' : 'HashIV'}
                            />
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <Label htmlFor={`${platform}-minamount`}>最低斗內金額 (NT$)</Label>
                          <Input
                            id={`${platform}-minamount`}
                            type="number"
                            min={1}
                            value={form.min_amount}
                            onChange={e =>
                              setPaymentForms(prev => ({
                                ...prev,
                                [platform]: { ...prev[platform], min_amount: e.target.value },
                              }))
                            }
                          />
                        </div>

                        <div className="flex items-center justify-between">
                          <Label htmlFor={`${platform}-media`}>允許點播 YouTube 影片</Label>
                          <Switch
                            id={`${platform}-media`}
                            checked={form.media_share_enabled}
                            onCheckedChange={checked =>
                              setPaymentForms(prev => ({
                                ...prev,
                                [platform]: { ...prev[platform], media_share_enabled: checked },
                              }))
                            }
                          />
                        </div>
                      </>
                    )}

                    <div className="flex items-center justify-between">
                      <Label htmlFor={`${platform}-enabled`}>啟用</Label>
                      <Switch
                        id={`${platform}-enabled`}
                        checked={form.enabled}
                        onCheckedChange={checked =>
                          setPaymentForms(prev => ({
                            ...prev,
                            [platform]: { ...prev[platform], enabled: checked },
                          }))
                        }
                      />
                    </div>

                    <div className="flex gap-2 pt-1">
                      <Button
                        className="flex-1"
                        onClick={() => handleSavePaymentConfig(platform)}
                        disabled={isSaving || isDeleting}
                      >
                        {isSaving && (
                          <Icon
                            icon="fa-solid fa-spinner"
                            className="animate-spin mr-2"
                            wrapperClassName=""
                          />
                        )}
                        儲存
                      </Button>
                      {existing && (
                        <Button
                          variant="outline"
                          onClick={() => handleDeletePaymentConfig(platform)}
                          disabled={isSaving || isDeleting}
                        >
                          {isDeleting ? (
                            <Icon
                              icon="fa-solid fa-spinner"
                              className="animate-spin"
                              wrapperClassName=""
                            />
                          ) : (
                            <Icon icon="fa-solid fa-trash" wrapperClassName="" />
                          )}
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  deletePaymentConfig,
  type DonationPlatform,
  getPaymentConfigs,
  NEEDS_HASH,
  type PaymentConfigResponse,
  PLATFORM_LABELS,
  upsertPaymentConfig,
} from '@/api'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsibleContent,
  Icon,
  Input,
  Label,
  Skeleton,
  Spinner,
  Switch,
} from '@/components/ui'
import { SlideUp, Stagger, StaggerItem } from '@/components/ui/motion'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

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
    enabled: false,
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
  const { user, isAffiliate } = useAuth()

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
  const [pendingDeletePlatform, setPendingDeletePlatform] = useState<DonationPlatform | null>(null)
  const [showHash, setShowHash] = useState<Record<DonationPlatform, boolean>>({
    ecpay: false,
    opay: false,
    newebpay: false,
    paypal: false,
  })

  const locked = !isAffiliate && user?.platform === 'twitch'

  const fetchPaymentConfigs = useCallback(async () => {
    try {
      setPaymentLoading(true)
      const configs = await getPaymentConfigs()
      setPaymentConfigs(configs)
      setPaymentForms(prev => {
        const updated = { ...prev }
        for (const c of configs) {
          if (Object.hasOwn(NEEDS_HASH, c.platform)) {
            updated[c.platform as DonationPlatform] = configToForm(c)
          }
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
        min_amount: (() => {
          const v = parseInt(form.min_amount, 10)
          return Number.isNaN(v) || v < 1 ? 30 : v
        })(),
        media_share_enabled: form.media_share_enabled,
        enabled: form.enabled,
      })
      toast.success(`已儲存 ${PLATFORM_LABELS[platform]} 設定`)
      await fetchPaymentConfigs()
    } catch {
      toast.error('儲存失敗', { description: '請稍後再試' })
    } finally {
      setPaymentSaving(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!pendingDeletePlatform) return
    const platform = pendingDeletePlatform
    setPendingDeletePlatform(null)
    setPaymentDeleting(platform)
    try {
      await deletePaymentConfig(platform)
      toast.success(`已刪除 ${PLATFORM_LABELS[platform]} 設定`)
      setPaymentForms(prev => ({ ...prev, [platform]: emptyForm() }))
      await fetchPaymentConfigs()
    } catch {
      toast.error('刪除失敗', { description: '請稍後再試' })
    } finally {
      setPaymentDeleting(null)
    }
  }

  return (
    <PageMain>
      <PageHeader title="Settings" description="金流設定" />

      <SlideUp inView>
        <Card className="relative overflow-hidden">
          {locked && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-background/80 backdrop-blur-sm rounded-[inherit]">
              <Icon
                icon="fa-solid fa-lock"
                className="text-5xl text-muted-foreground"
                wrapperClassName="size-16"
              />
              <span className="text-sm text-muted-foreground">
                成為 Twitch 聯盟夥伴或合作夥伴後即可設定金流
              </span>
            </div>
          )}
          <CardHeader>
            <CardTitle>斗內金流設定</CardTitle>
            <CardDescription>
              設定收款帳號以啟用斗內功能，觀眾可透過{' '}
              <code className="text-foreground">/donate/{user?.name}</code> 贊助
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-section">
            {paymentLoading ? (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : (
              <Stagger inView className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-start">
                {ALL_PLATFORMS.map(platform => {
                  const form = paymentForms[platform]
                  const existing = paymentConfigs.find(c => c.platform === platform)
                  const needsHash = NEEDS_HASH[platform]
                  const label = PLATFORM_LABELS[platform]
                  const isSaving = paymentSaving === platform
                  const isDeleting = paymentDeleting === platform

                  return (
                    <StaggerItem key={platform}>
                      <Card>
                        <CardHeader>
                          <div className="flex items-center gap-element">
                            <CardTitle className="text-sub">{label}</CardTitle>
                            {existing && (
                              <Badge variant="secondary" className="text-label">
                                已設定
                              </Badge>
                            )}
                          </div>
                          <CardAction>
                            <div className="flex items-center gap-2">
                              {existing && (
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  onClick={() => setPendingDeletePlatform(platform)}
                                  disabled={isSaving || isDeleting || locked}
                                  className="text-muted-foreground hover:text-destructive"
                                  aria-label={`刪除 ${label} 設定`}
                                >
                                  {isDeleting ? (
                                    <Spinner />
                                  ) : (
                                    <Icon icon="fa-solid fa-trash" wrapperClassName="size-3.5" />
                                  )}
                                </Button>
                              )}
                              <Switch
                                id={`${platform}-enabled`}
                                aria-label="啟用"
                                checked={form.enabled}
                                disabled={locked}
                                onCheckedChange={checked =>
                                  setPaymentForms(prev => ({
                                    ...prev,
                                    [platform]: { ...prev[platform], enabled: checked },
                                  }))
                                }
                              />
                            </div>
                          </CardAction>
                        </CardHeader>

                        <Collapsible open={form.enabled}>
                          <CollapsibleContent>
                            <CardContent className="flex flex-col gap-3 pt-0">
                              {/* MerchantID (full width) */}
                              <div className="flex flex-col gap-1">
                                <Label
                                  className="text-label text-muted-foreground"
                                  htmlFor={`${platform}-merchant`}
                                >
                                  {platform === 'paypal' ? 'PayPal.me URL' : '商店代號'}
                                </Label>
                                <Input
                                  id={`${platform}-merchant`}
                                  value={form.merchant_id}
                                  disabled={locked}
                                  onChange={e =>
                                    setPaymentForms(prev => ({
                                      ...prev,
                                      [platform]: {
                                        ...prev[platform],
                                        merchant_id: e.target.value,
                                      },
                                    }))
                                  }
                                  placeholder={
                                    platform === 'paypal' ? 'paypal.me/yourname' : '商店代號'
                                  }
                                  className="h-8 text-sub"
                                />
                              </div>

                              {/* HashKey + HashIV (2 cols) */}
                              {needsHash && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-element">
                                  <div className="flex flex-col gap-1">
                                    <Label
                                      className="text-label text-muted-foreground"
                                      htmlFor={`${platform}-hashkey`}
                                    >
                                      HashKey{existing?.has_hash ? ' (留空不變)' : ''}
                                    </Label>
                                    <div className="relative">
                                      <Input
                                        id={`${platform}-hashkey`}
                                        type={showHash[platform] ? 'text' : 'password'}
                                        value={form.hash_key}
                                        disabled={locked}
                                        onChange={e =>
                                          setPaymentForms(prev => ({
                                            ...prev,
                                            [platform]: {
                                              ...prev[platform],
                                              hash_key: e.target.value,
                                            },
                                          }))
                                        }
                                        placeholder={existing?.has_hash ? '••••••••' : 'HashKey'}
                                        className="h-8 text-sub pr-8"
                                      />
                                      <button
                                        type="button"
                                        aria-label={showHash[platform] ? '隱藏金鑰' : '顯示金鑰'}
                                        onClick={() =>
                                          setShowHash(prev => ({
                                            ...prev,
                                            [platform]: !prev[platform],
                                          }))
                                        }
                                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                      >
                                        <Icon
                                          icon={
                                            showHash[platform]
                                              ? 'fa-solid fa-eye-slash'
                                              : 'fa-solid fa-eye'
                                          }
                                          wrapperClassName="size-3.5"
                                        />
                                      </button>
                                    </div>
                                  </div>
                                  <div className="flex flex-col gap-1">
                                    <Label
                                      className="text-label text-muted-foreground"
                                      htmlFor={`${platform}-hashiv`}
                                    >
                                      HashIV{existing?.has_hash ? ' (留空不變)' : ''}
                                    </Label>
                                    <div className="relative">
                                      <Input
                                        id={`${platform}-hashiv`}
                                        type={showHash[platform] ? 'text' : 'password'}
                                        value={form.hash_iv}
                                        disabled={locked}
                                        onChange={e =>
                                          setPaymentForms(prev => ({
                                            ...prev,
                                            [platform]: {
                                              ...prev[platform],
                                              hash_iv: e.target.value,
                                            },
                                          }))
                                        }
                                        placeholder={existing?.has_hash ? '••••••••' : 'HashIV'}
                                        className="h-8 text-sub pr-8"
                                      />
                                      <button
                                        type="button"
                                        aria-label={showHash[platform] ? '隱藏金鑰' : '顯示金鑰'}
                                        onClick={() =>
                                          setShowHash(prev => ({
                                            ...prev,
                                            [platform]: !prev[platform],
                                          }))
                                        }
                                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                      >
                                        <Icon
                                          icon={
                                            showHash[platform]
                                              ? 'fa-solid fa-eye-slash'
                                              : 'fa-solid fa-eye'
                                          }
                                          wrapperClassName="size-3.5"
                                        />
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              )}

                              {/* Bottom: min amount + media toggle + save */}
                              <div className="flex flex-wrap items-center gap-x-element gap-y-2 border-t border-border/50 pt-2">
                                {needsHash && (
                                  <>
                                    <span className="text-label text-muted-foreground shrink-0">
                                      最低
                                    </span>
                                    <Input
                                      id={`${platform}-minamount`}
                                      type="number"
                                      min={1}
                                      value={form.min_amount}
                                      disabled={locked}
                                      onChange={e =>
                                        setPaymentForms(prev => ({
                                          ...prev,
                                          [platform]: {
                                            ...prev[platform],
                                            min_amount: e.target.value,
                                          },
                                        }))
                                      }
                                      className="h-7 w-16 text-label"
                                    />
                                    <span className="text-label text-muted-foreground shrink-0">
                                      NT$
                                    </span>
                                    <div className="flex items-center gap-1 ml-1">
                                      <Switch
                                        id={`${platform}-media`}
                                        checked={form.media_share_enabled}
                                        disabled={locked}
                                        onCheckedChange={checked =>
                                          setPaymentForms(prev => ({
                                            ...prev,
                                            [platform]: {
                                              ...prev[platform],
                                              media_share_enabled: checked,
                                            },
                                          }))
                                        }
                                      />
                                      <Label
                                        htmlFor={`${platform}-media`}
                                        className="text-label cursor-pointer whitespace-nowrap"
                                      >
                                        影片點播
                                      </Label>
                                    </div>
                                  </>
                                )}
                                <div className="flex gap-1.5 ml-auto">
                                  <Button
                                    size="sm"
                                    onClick={() => handleSavePaymentConfig(platform)}
                                    disabled={isSaving || isDeleting || locked}
                                    className="h-7 px-3 text-label"
                                  >
                                    {isSaving && <Spinner className="mr-1" />}
                                    儲存
                                  </Button>
                                </div>
                              </div>
                            </CardContent>
                          </CollapsibleContent>
                        </Collapsible>
                      </Card>
                    </StaggerItem>
                  )
                })}
              </Stagger>
            )}
          </CardContent>
        </Card>
      </SlideUp>

      {/* Delete confirmation dialog */}
      <AlertDialog
        open={!!pendingDeletePlatform}
        onOpenChange={(open: boolean) => !open && setPendingDeletePlatform(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>確定刪除設定？</AlertDialogTitle>
            <AlertDialogDescription>
              即將刪除{' '}
              <span className="font-medium text-foreground">
                {pendingDeletePlatform ? PLATFORM_LABELS[pendingDeletePlatform] : ''}
              </span>{' '}
              的金流設定，此操作無法還原。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleConfirmDelete}
            >
              刪除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageMain>
  )
}

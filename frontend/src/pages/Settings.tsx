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
  Switch,
} from '@/components/ui'
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
  const { user } = useAuth()

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
    } catch (err) {
      toast.error('儲存失敗', { description: err instanceof Error ? err.message : '請稍後再試' })
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
    } catch (err) {
      toast.error('刪除失敗', { description: err instanceof Error ? err.message : '請稍後再試' })
    } finally {
      setPaymentDeleting(null)
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
      <PageHeader title="Settings" description="金流設定" />

      <Card>
        <CardHeader>
          <CardTitle>斗內金流設定</CardTitle>
          <CardDescription>
            設定收款帳號以啟用斗內功能，觀眾可透過{' '}
            <code className="text-foreground">/donate/{user?.name}</code> 贊助
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-section">
          {paymentLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-start">
              {ALL_PLATFORMS.map(platform => {
                const form = paymentForms[platform]
                const existing = paymentConfigs.find(c => c.platform === platform)
                const needsHash = NEEDS_HASH[platform]
                const label = PLATFORM_LABELS[platform]
                const isSaving = paymentSaving === platform
                const isDeleting = paymentDeleting === platform

                return (
                  <div key={platform} className="rounded-lg border p-card">
                    {/* Header: name + enabled toggle */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-element">
                        <span className="font-medium text-sub">{label}</span>
                        {existing && (
                          <Badge variant="secondary" className="text-label">
                            已設定
                          </Badge>
                        )}
                      </div>
                      <Switch
                        id={`${platform}-enabled`}
                        aria-label="啟用"
                        checked={form.enabled}
                        onCheckedChange={checked =>
                          setPaymentForms(prev => ({
                            ...prev,
                            [platform]: { ...prev[platform], enabled: checked },
                          }))
                        }
                      />
                    </div>

                    <Collapsible open={form.enabled}>
                      <CollapsibleContent>
                        <div className="mt-element space-y-3">
                          {/* MerchantID (full width) */}
                          <div className="space-y-1">
                            <Label
                              className="text-label text-muted-foreground"
                              htmlFor={`${platform}-merchant`}
                            >
                              {platform === 'paypal' ? 'PayPal.me URL' : '商店代號'}
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
                                platform === 'paypal' ? 'paypal.me/yourname' : '商店代號'
                              }
                              className="h-8 text-sub"
                            />
                          </div>

                          {/* HashKey + HashIV (2 cols) */}
                          {needsHash && (
                            <div className="grid grid-cols-2 gap-element">
                              <div className="space-y-1">
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
                                    onChange={e =>
                                      setPaymentForms(prev => ({
                                        ...prev,
                                        [platform]: { ...prev[platform], hash_key: e.target.value },
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
                                      wrapperClassName=""
                                      className="text-label"
                                    />
                                  </button>
                                </div>
                              </div>
                              <div className="space-y-1">
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
                                    onChange={e =>
                                      setPaymentForms(prev => ({
                                        ...prev,
                                        [platform]: { ...prev[platform], hash_iv: e.target.value },
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
                                      wrapperClassName=""
                                      className="text-label"
                                    />
                                  </button>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Bottom: min amount + media toggle + save/delete */}
                          <div className="flex items-center gap-element border-t border-border/50 pt-2">
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
                                  onChange={e =>
                                    setPaymentForms(prev => ({
                                      ...prev,
                                      [platform]: { ...prev[platform], min_amount: e.target.value },
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
                                disabled={isSaving || isDeleting}
                                className="h-7 px-3 text-label"
                              >
                                {isSaving && (
                                  <Icon
                                    icon="fa-solid fa-spinner"
                                    className="animate-spin mr-1"
                                    wrapperClassName=""
                                  />
                                )}
                                儲存
                              </Button>
                              {existing && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => setPendingDeletePlatform(platform)}
                                  disabled={isSaving || isDeleting}
                                  className="h-7 px-2"
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
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

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
    </main>
  )
}

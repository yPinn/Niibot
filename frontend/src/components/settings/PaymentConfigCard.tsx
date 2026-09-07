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
} from '@/api/donation'
import { AffiliateLockOverlay } from '@/components/AffiliateLockOverlay'
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { SlideUp, Stagger, StaggerItem } from '@/components/primitives'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useTenant } from '@/contexts/TenantContext'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { toastApiError } from '@/lib/toast-error'

import { emptyForm, type PaymentFormState, PaymentPlatformCard } from './PaymentPlatformCard'

const ALL_PLATFORMS: DonationPlatform[] = ['ecpay', 'opay', 'newebpay', 'paypal']

function configToForm(c: PaymentConfigResponse): PaymentFormState {
  return {
    merchant_id: c.merchant_id,
    hash_key: '',
    hash_iv: '',
    min_amount: String(c.min_amount),
    media_share_enabled: c.media_share_enabled,
  }
}

type PlatformFlags = Record<DonationPlatform, boolean>
const NO_FLAGS: PlatformFlags = { ecpay: false, opay: false, newebpay: false, paypal: false }

export function PaymentConfigCard() {
  const { user, isAffiliate } = useAuth()
  const { activeTenant } = useTenant()
  const canManageBilling = activeTenant?.capabilities.includes('manage_billing') ?? false

  const [configs, setConfigs] = useState<PaymentConfigResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [forms, setForms] = useState<Record<DonationPlatform, PaymentFormState>>({
    ecpay: emptyForm(),
    opay: emptyForm(),
    newebpay: emptyForm(),
    paypal: emptyForm(),
  })
  const [saving, setSaving] = useState<DonationPlatform | null>(null)
  const [deleting, setDeleting] = useState<DonationPlatform | null>(null)
  const [pendingDelete, setPendingDelete] = useState<DonationPlatform | null>(null)
  const [revealed, setRevealed] = useState<PlatformFlags>(NO_FLAGS)
  const [open, setOpen] = useState<PlatformFlags>(NO_FLAGS)

  const locked = !isAffiliate && user?.platform === 'twitch'

  const patchForm = useCallback((platform: DonationPlatform, patch: Partial<PaymentFormState>) => {
    setForms(prev => ({ ...prev, [platform]: { ...prev[platform], ...patch } }))
  }, [])

  const { toggle: toggleEnabled } = useOptimisticToggle<PaymentConfigResponse>({
    setState: setConfigs,
    getId: c => c.platform,
    toggleFn: (c, enabled) =>
      upsertPaymentConfig(c.platform, {
        merchant_id: c.merchant_id,
        min_amount: c.min_amount,
        media_share_enabled: c.media_share_enabled,
        enabled,
      }),
    messages: { on: '已啟用', off: '已停用', error: '切換狀態失敗' },
  })

  const fetchConfigs = useCallback(async () => {
    try {
      setLoading(true)
      const next = await getPaymentConfigs()
      setConfigs(next)
      setForms(prev => {
        const updated = { ...prev }
        for (const c of next) {
          if (Object.hasOwn(NEEDS_HASH, c.platform)) {
            updated[c.platform as DonationPlatform] = configToForm(c)
          }
        }
        return updated
      })
    } catch (e) {
      toastApiError(e, '無法載入金流設定')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!canManageBilling) return
    const timeoutId = window.setTimeout(() => void fetchConfigs(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [canManageBilling, fetchConfigs])

  const handleSave = async (platform: DonationPlatform) => {
    const form = forms[platform]
    setSaving(platform)
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
        // New platforms go live on first save; editing an existing one keeps
        // whatever the enable toggle last set.
        enabled: configs.find(c => c.platform === platform)?.enabled ?? true,
      })
      toast.success(`已儲存 ${PLATFORM_LABELS[platform]} 設定`)
      await fetchConfigs()
    } catch (e) {
      toastApiError(e, '儲存失敗')
    } finally {
      setSaving(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return
    const platform = pendingDelete
    setPendingDelete(null)
    setDeleting(platform)
    try {
      await deletePaymentConfig(platform)
      toast.success(`已刪除 ${PLATFORM_LABELS[platform]} 設定`)
      setForms(prev => ({ ...prev, [platform]: emptyForm() }))
      await fetchConfigs()
    } catch (e) {
      toastApiError(e, '刪除失敗')
    } finally {
      setDeleting(null)
    }
  }

  if (!canManageBilling) return null

  return (
    <SlideUp inView>
      <Card className="relative overflow-hidden">
        {locked && (
          <AffiliateLockOverlay message="取得資格後可設定金流方式" className="rounded-[inherit]" />
        )}
        <CardHeader>
          <CardTitle>斗內金流設定</CardTitle>
          <CardDescription>
            設定收款帳號以啟用斗內功能，觀眾可透過{' '}
            <a
              href={`/donate/${user?.name}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-foreground underline-offset-2 hover:underline"
            >
              /donate/{user?.name}
            </a>{' '}
            贊助
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-section">
          {loading ? (
            <div className="flex flex-col gap-section">
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : (
            <Stagger inView className="grid grid-cols-1 sm:grid-cols-2 gap-section items-start">
              {ALL_PLATFORMS.map(platform => {
                const existing = configs.find(c => c.platform === platform)
                return (
                  <StaggerItem key={platform}>
                    <PaymentPlatformCard
                      platform={platform}
                      form={forms[platform]}
                      hasExisting={!!existing}
                      hasStoredHash={!!existing?.has_hash}
                      enabled={existing?.enabled ?? false}
                      isSaving={saving === platform}
                      isDeleting={deleting === platform}
                      locked={locked}
                      isOpen={open[platform]}
                      revealed={revealed[platform]}
                      onToggleOpen={() => setOpen(p => ({ ...p, [platform]: !p[platform] }))}
                      onToggleReveal={() => setRevealed(p => ({ ...p, [platform]: !p[platform] }))}
                      onToggleEnabled={() => existing && void toggleEnabled(existing)}
                      onPatch={patch => patchForm(platform, patch)}
                      onSave={() => void handleSave(platform)}
                      onRequestDelete={() => setPendingDelete(platform)}
                    />
                  </StaggerItem>
                )
              })}
            </Stagger>
          )}
        </CardContent>
      </Card>

      <DeleteConfirmDialog
        open={!!pendingDelete}
        onOpenChange={(o: boolean) => !o && setPendingDelete(null)}
        title="確定刪除設定？"
        description={
          <>
            即將刪除{' '}
            <span className="font-medium text-foreground">
              {pendingDelete ? PLATFORM_LABELS[pendingDelete] : ''}
            </span>{' '}
            的金流設定，此操作無法還原。
          </>
        }
        onConfirm={handleConfirmDelete}
      />
    </SlideUp>
  )
}

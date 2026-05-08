import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  type CheckoutRequest,
  createCheckout,
  type DonationPlatform,
  getPublicDonateInfo,
  NEEDS_HASH,
  PLATFORM_LABELS,
  type PublicDonateInfo,
  type PublicPlatformInfo,
} from '@/api/donation'
import {
  Button,
  Card,
  CardContent,
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Icon,
  Input,
  SlideUp,
  SlideUpSm,
  Spinner,
  Stagger,
  StaggerItem,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ============================================================
// Auto-submit payment form helper
// ============================================================

function submitPaymentForm(gatewayUrl: string, params: Record<string, string>) {
  if (!gatewayUrl.startsWith('https://')) {
    throw new Error(`Invalid gateway URL: must use HTTPS`)
  }
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = gatewayUrl
  form.style.display = 'none'
  for (const [key, value] of Object.entries(params)) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = key
    input.value = value
    form.appendChild(input)
  }
  document.body.appendChild(form)
  form.submit()
}

// ============================================================
// Platform card
// ============================================================

interface PlatformCardProps {
  platform: PublicPlatformInfo
  username: string
}

function PlatformCard({ platform, username }: PlatformCardProps) {
  const [amount, setAmount] = useState(platform.min_amount.toString())
  const [message, setMessage] = useState('')
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDonate = useCallback(async () => {
    const numAmount = parseInt(amount, 10)
    if (isNaN(numAmount) || numAmount < platform.min_amount) {
      setError(`最低斗內金額 NT$${platform.min_amount}`)
      return
    }

    setError(null)
    setLoading(true)

    try {
      const req: CheckoutRequest = {
        platform: platform.platform as DonationPlatform,
        amount: numAmount,
        message: message.trim() || undefined,
        youtube_url: youtubeUrl.trim() || undefined,
        return_url: window.location.href,
      }

      const checkout = await createCheckout(username, req)

      // PayPal: simple redirect
      if (platform.platform === 'paypal' || Object.keys(checkout.form_params).length === 0) {
        if (!checkout.gateway_url.startsWith('https://')) {
          setError('無效的付款網址')
          setLoading(false)
          return
        }
        window.location.href = checkout.gateway_url
        return
      }

      // ECPay / OPay: auto-submit signed form
      submitPaymentForm(checkout.gateway_url, checkout.form_params)
    } catch (e) {
      setError(e instanceof Error ? e.message : '建立付款失敗，請稍後再試')
      setLoading(false)
    }
  }, [amount, message, youtubeUrl, platform, username])

  const platformLabel = PLATFORM_LABELS[platform.platform as DonationPlatform] ?? platform.platform
  const needsHash = NEEDS_HASH[platform.platform as DonationPlatform] ?? false

  return (
    <Card>
      <CardContent className="pt-5 space-y-3">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-base">{platformLabel}</span>
        </div>

        {needsHash ? (
          <>
            <div className="flex items-center gap-2">
              <span className="text-sub text-muted-foreground w-14 shrink-0">金額</span>
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sub">
                  NT$
                </span>
                <Input
                  type="number"
                  min={platform.min_amount}
                  value={amount}
                  onChange={e => setAmount(e.target.value)}
                  className="pl-10"
                  placeholder={`最低 ${platform.min_amount}`}
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sub text-muted-foreground w-14 shrink-0">留言</span>
              <Input
                value={message}
                onChange={e => setMessage(e.target.value.slice(0, 50))}
                placeholder="留下訊息（選填，最多 50 字）"
                maxLength={50}
              />
            </div>

            {platform.media_share_enabled && (
              <div className="flex items-center gap-2">
                <span className="text-sub text-muted-foreground w-14 shrink-0">點播</span>
                <Input
                  value={youtubeUrl}
                  onChange={e => setYoutubeUrl(e.target.value)}
                  placeholder="YouTube 連結（選填）"
                />
              </div>
            )}
          </>
        ) : (
          <p className="text-sub text-muted-foreground">點擊前往 PayPal 付款頁面</p>
        )}

        {error && <p className="text-sub text-destructive">{error}</p>}

        <Button className="w-full" onClick={handleDonate} disabled={loading}>
          {loading ? <Spinner className="mr-2 h-4 w-4" /> : null}
          {platform.platform === 'paypal' ? '前往 PayPal' : '前往付款'}
        </Button>
      </CardContent>
    </Card>
  )
}

// ============================================================
// Main page
// ============================================================

export default function DonatePage() {
  const { username } = useParams<{ username: string }>()
  const [info, setInfo] = useState<PublicDonateInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useDocumentTitle(info ? `斗內 ${info.username}` : '斗內')

  useEffect(() => {
    if (!username) return
    async function load() {
      setLoading(true)
      try {
        setInfo(await getPublicDonateInfo(username!))
      } catch (e: unknown) {
        if (e instanceof Error && e.message === 'Streamer not found') setNotFound(true)
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [username])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    )
  }

  if (notFound || !info) {
    return (
      <Empty className="border-none min-h-screen">
        <EmptyHeader>
          <EmptyMedia>
            <Icon
              icon="fa-solid fa-circle-xmark"
              wrapperClassName="size-20 opacity-25"
              className="text-[5rem]"
            />
          </EmptyMedia>
          <EmptyTitle>找不到這位實況主</EmptyTitle>
        </EmptyHeader>
      </Empty>
    )
  }

  if (info.platforms.length === 0) {
    return (
      <Empty className="border-none min-h-screen">
        <EmptyHeader>
          <EmptyMedia>
            <Icon
              icon="fa-solid fa-ban"
              wrapperClassName="size-20 opacity-25"
              className="text-[5rem]"
            />
          </EmptyMedia>
          <EmptyTitle>{info.username} 尚未開啟斗內功能</EmptyTitle>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center py-10 px-4">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <SlideUpSm className="text-center space-y-1">
          <h1 className="text-2xl font-bold">支持 {info.display_name ?? info.username}</h1>
          <p className="text-sub text-muted-foreground">選擇付款方式完成斗內</p>
        </SlideUpSm>

        {/* Platform cards */}
        <Stagger delayChildren={0.1} className="space-y-4">
          {info.platforms.map(p => (
            <StaggerItem key={p.platform}>
              <PlatformCard platform={p} username={info.username} />
            </StaggerItem>
          ))}
        </Stagger>

        <SlideUp delay={0.2}>
          <p className="text-xs text-center text-muted-foreground">
            付款由{' '}
            {info.platforms
              .map(p => PLATFORM_LABELS[p.platform as DonationPlatform] ?? p.platform)
              .join(' / ')}{' '}
            處理，Niibot 不儲存信用卡資訊。
          </p>
        </SlideUp>
      </div>
    </div>
  )
}

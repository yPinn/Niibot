import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { getLinkedAccounts, type LinkedAccount, openOAuthLink, unlinkAccount } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Separator,
  Skeleton,
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

export default function Settings() {
  useDocumentTitle('Settings')
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [accounts, setAccounts] = useState<LinkedAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [unlinking, setUnlinking] = useState<string | null>(null)

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

  // Handle URL query params from OAuth redirect
  useEffect(() => {
    const linked = searchParams.get('linked')
    const error = searchParams.get('error')

    if (linked) {
      toast.success('帳號連結成功', {
        description: `已連結 ${PLATFORM_CONFIG[linked as keyof typeof PLATFORM_CONFIG]?.label ?? linked} 帳號`,
      })
      setSearchParams({}, { replace: true })
      fetchAccounts()
    }

    if (error) {
      toast.error('帳號連結失敗', {
        description: ERROR_MESSAGES[error] || `連結失敗 (${error})`,
      })
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams, fetchAccounts])

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

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
      <div>
        <h1 className="text-page-title font-bold">設定 (Settings)</h1>
        <p className="text-sub text-muted-foreground">管理帳號設定與偏好</p>
      </div>

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
    </main>
  )
}

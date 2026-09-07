import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  type BotAccount,
  type BotInviteCreated,
  createBotInvite,
  createBotReauthorizationInvite,
  getBotInviteStatus,
  listBotAccounts,
} from '@/api/botAccounts'
import { Icon, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Skeleton,
} from '@/components/ui'
import { useTenant } from '@/contexts/TenantContext'
import { toastApiError } from '@/lib/toast-error'

export function BotAccountsCard() {
  const { activeTenant } = useTenant()
  const [accounts, setAccounts] = useState<BotAccount[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [invite, setInvite] = useState<BotInviteCreated | null>(null)
  const [inviteStatus, setInviteStatus] = useState<
    'pending' | 'authorized' | 'declined' | 'expired' | null
  >(null)
  const canManage = activeTenant?.capabilities.includes('manage_bot_accounts') ?? false

  const loadAccounts = useCallback(async () => {
    if (!activeTenant) return
    setLoading(true)
    try {
      setAccounts(await listBotAccounts(activeTenant.channel_id))
    } catch (error) {
      toastApiError(error, '載入 Bot 帳號失敗')
    } finally {
      setLoading(false)
    }
  }, [activeTenant])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadAccounts(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [loadAccounts])

  useEffect(() => {
    if (!activeTenant || !invite || inviteStatus !== 'pending') return
    const poll = async () => {
      try {
        const next = await getBotInviteStatus(activeTenant.channel_id, invite.invite_id)
        setInviteStatus(next.status)
        if (next.status === 'authorized') await loadAccounts()
      } catch {
        // A transient polling failure must not discard the one-time URL.
      }
    }
    const intervalId = window.setInterval(() => void poll(), 2500)
    return () => window.clearInterval(intervalId)
  }, [activeTenant, invite, inviteStatus, loadAccounts])

  const createInvite = async () => {
    if (!activeTenant) return
    setCreating(true)
    try {
      const created = await createBotInvite(activeTenant.channel_id)
      setInvite(created)
      setInviteStatus('pending')
    } catch (error) {
      toastApiError(error, '建立 Bot 邀請失敗')
    } finally {
      setCreating(false)
    }
  }

  const reauthorize = async (botUserId: string) => {
    if (!activeTenant) return
    setCreating(true)
    try {
      const created = await createBotReauthorizationInvite(activeTenant.channel_id, botUserId)
      setInvite(created)
      setInviteStatus('pending')
    } catch (error) {
      toastApiError(error, '建立重新授權邀請失敗')
    } finally {
      setCreating(false)
    }
  }

  const copyInvite = async () => {
    if (!invite) return
    try {
      await navigator.clipboard.writeText(invite.public_url)
      toast.success('Bot 邀請連結已複製')
    } catch {
      toast.error('無法複製，請手動選取連結')
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon="fa-solid fa-robot" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle>Bot 帳號</CardTitle>
        </div>
        <CardDescription>
          每個工作區只會看見 Niibot 與自己邀請的帳號；Bot 授權不會授予 Dashboard 權限。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-section">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : accounts.length === 0 ? (
          <p className="rounded-lg border border-dashed p-section text-sub text-muted-foreground">
            尚未設定可用的 Bot 帳號。
          </p>
        ) : (
          <ul className="space-y-2" aria-label="可用 Bot 帳號">
            {accounts.map(account => (
              <li
                key={account.platform_user_id}
                className="flex items-center gap-3 rounded-lg border px-3 py-2"
              >
                {account.avatar ? (
                  <img
                    src={account.avatar}
                    alt=""
                    className="size-9 shrink-0 rounded-full object-cover"
                  />
                ) : (
                  <div className="grid size-9 shrink-0 place-items-center rounded-full bg-muted">
                    <Icon icon="fa-solid fa-robot" size="sm" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">{account.display_name}</span>
                    {account.is_system_default && <Badge variant="secondary">系統預設</Badge>}
                    {account.requires_reauth && <Badge variant="destructive">需要重新授權</Badge>}
                  </div>
                  <p className="truncate font-mono text-label text-muted-foreground">
                    @{account.login}
                  </p>
                </div>
                {canManage && !account.is_system_default && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void reauthorize(account.platform_user_id)}
                    disabled={creating}
                    aria-label={`重新授權 ${account.display_name}`}
                  >
                    重新授權
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}

        {canManage && (
          <div className="space-y-3 border-t pt-section">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sub font-medium">邀請其他 Twitch 帳號</p>
                <p className="text-label text-muted-foreground">
                  連結 30 分鐘內有效，只能使用一次。
                </p>
              </div>
              <Button onClick={() => void createInvite()} disabled={creating}>
                {creating ? (
                  <Spinner className="mr-2" />
                ) : (
                  <Icon icon="fa-solid fa-link" size="xs" />
                )}
                邀請 Bot 帳號
              </Button>
            </div>

            {invite && (
              <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-label font-medium">
                    {inviteStatus === 'authorized'
                      ? '已完成授權'
                      : inviteStatus === 'pending'
                        ? '等待對方授權'
                        : '邀請已結束'}
                  </p>
                  {inviteStatus === 'pending' && <Spinner />}
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input value={invite.public_url} readOnly aria-label="Bot 邀請 URL" />
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => void copyInvite()}>
                      複製
                    </Button>
                    <Button variant="outline" asChild>
                      <a href={invite.public_url} target="_blank" rel="noopener noreferrer">
                        開啟
                      </a>
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  type BotAccount,
  type BotInviteCreated,
  type BroadcasterAuthorization,
  checkBotAuthorization,
  checkBroadcasterAuthorization,
  createBotInvite,
  createBotReauthorizationInvite,
  disconnectBroadcasterAuthorization,
  getBotInviteStatus,
  getBroadcasterAuthorization,
  listBotAccounts,
  type TwitchAuthorizationStatus,
  unlinkBotAccount,
} from '@/api/botAccounts'
import { openTwitchOAuth } from '@/api/twitchOAuth'
import { Icon, Spinner } from '@/components/primitives'
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
  Input,
  Skeleton,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { useTenant } from '@/contexts/TenantContext'
import { toastApiError } from '@/lib/toast-error'

type ConfirmationTarget = { kind: 'bot'; account: BotAccount } | { kind: 'broadcaster' } | null

const STATUS_COPY: Record<
  TwitchAuthorizationStatus,
  { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  valid: { label: '授權正常', variant: 'secondary' },
  requires_reauthorization: { label: '需要重新授權', variant: 'destructive' },
  temporarily_unavailable: { label: '暫時無法確認', variant: 'outline' },
  not_checked: { label: '尚未確認', variant: 'outline' },
}

function AuthorizationBadge({ status }: { status: TwitchAuthorizationStatus }) {
  const copy = STATUS_COPY[status]
  return <Badge variant={copy.variant}>{copy.label}</Badge>
}

function IconAction({
  label,
  tooltip,
  icon,
  busy = false,
  disabled = false,
  onClick,
}: {
  label: string
  tooltip: string
  icon: string
  busy?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="icon-sm"
          variant="outline"
          aria-label={label}
          disabled={disabled}
          onClick={onClick}
        >
          {busy ? <Spinner /> : <Icon icon={icon} size="sm" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  )
}

function lastCheckedText(value: string | null): string {
  if (!value) return '尚未檢查'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '檢查時間未知'
  return `上次確認：${new Intl.DateTimeFormat('zh-TW', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)}`
}

export function BotAccountsCard() {
  const { activeTenant } = useTenant()
  const [accounts, setAccounts] = useState<BotAccount[]>([])
  const [broadcaster, setBroadcaster] = useState<BroadcasterAuthorization | null>(null)
  const [accountsLoading, setAccountsLoading] = useState(false)
  const [broadcasterLoading, setBroadcasterLoading] = useState(false)
  const [accountsLoadFailed, setAccountsLoadFailed] = useState(false)
  const [broadcasterLoadFailed, setBroadcasterLoadFailed] = useState(false)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [invite, setInvite] = useState<BotInviteCreated | null>(null)
  const [inviteStatus, setInviteStatus] = useState<
    'pending' | 'authorized' | 'declined' | 'expired' | null
  >(null)
  const [confirmation, setConfirmation] = useState<ConfirmationTarget>(null)
  const [channelConfirmation, setChannelConfirmation] = useState('')
  const canManage = activeTenant?.capabilities.includes('manage_bot_accounts') ?? false

  const loadAccounts = useCallback(async () => {
    if (!activeTenant) return
    setAccountsLoading(true)
    setAccountsLoadFailed(false)
    try {
      setAccounts(await listBotAccounts(activeTenant.channel_id))
    } catch {
      setAccountsLoadFailed(true)
    } finally {
      setAccountsLoading(false)
    }
  }, [activeTenant])

  const loadBroadcaster = useCallback(async () => {
    if (!activeTenant) return
    setBroadcasterLoading(true)
    setBroadcasterLoadFailed(false)
    try {
      setBroadcaster(await getBroadcasterAuthorization(activeTenant.channel_id))
    } catch {
      setBroadcasterLoadFailed(true)
    } finally {
      setBroadcasterLoading(false)
    }
  }, [activeTenant])

  const loadAuthorizations = useCallback(
    async () => Promise.allSettled([loadAccounts(), loadBroadcaster()]),
    [loadAccounts, loadBroadcaster]
  )

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadAuthorizations(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [loadAuthorizations])

  useEffect(() => {
    if (!activeTenant || !invite || inviteStatus !== 'pending') return
    const poll = async () => {
      try {
        const next = await getBotInviteStatus(activeTenant.channel_id, invite.invite_id)
        setInviteStatus(next.status)
        if (next.status === 'authorized') await loadAuthorizations()
      } catch {
        // Keep the one-time URL visible when polling fails temporarily.
      }
    }
    const intervalId = window.setInterval(() => void poll(), 2500)
    return () => window.clearInterval(intervalId)
  }, [activeTenant, invite, inviteStatus, loadAuthorizations])

  const createInvite = async () => {
    if (!activeTenant) return
    setBusyAction('create-invite')
    try {
      const created = await createBotInvite(activeTenant.channel_id)
      setInvite(created)
      setInviteStatus('pending')
    } catch (error) {
      toastApiError(error, '建立 Bot 邀請失敗')
    } finally {
      setBusyAction(null)
    }
  }

  const reauthorizeBot = async (account: BotAccount) => {
    if (!activeTenant) return
    setBusyAction(`reauthorize:${account.platform_user_id}`)
    try {
      const created = await createBotReauthorizationInvite(
        activeTenant.channel_id,
        account.platform_user_id
      )
      setInvite(created)
      setInviteStatus('pending')
    } catch (error) {
      toastApiError(error, '建立重新授權邀請失敗')
    } finally {
      setBusyAction(null)
    }
  }

  const checkBot = async (account: BotAccount) => {
    if (!activeTenant) return
    setBusyAction(`check:${account.platform_user_id}`)
    try {
      const health = await checkBotAuthorization(activeTenant.channel_id, account.platform_user_id)
      setAccounts(current =>
        current.map(item =>
          item.platform_user_id === account.platform_user_id
            ? {
                ...item,
                authorization_status: health.status,
                last_checked_at: health.last_checked_at,
                last_validated_at: health.last_validated_at,
                requires_reauth: health.status === 'requires_reauthorization',
              }
            : item
        )
      )
      toast.success('已重新確認 Bot 授權')
    } catch (error) {
      toastApiError(error, '重新檢查 Bot 授權失敗')
    } finally {
      setBusyAction(null)
    }
  }

  const checkBroadcaster = async () => {
    if (!activeTenant || !broadcaster) return
    setBusyAction('check:broadcaster')
    try {
      const health = await checkBroadcasterAuthorization(activeTenant.channel_id)
      setBroadcaster({ ...broadcaster, ...health })
      toast.success('已重新確認實況主授權')
    } catch (error) {
      toastApiError(error, '重新檢查 Twitch 授權失敗')
    } finally {
      setBusyAction(null)
    }
  }

  const reauthorizeBroadcaster = async () => {
    setBusyAction('reauthorize:broadcaster')
    try {
      await openTwitchOAuth()
    } catch (error) {
      toastApiError(error, '無法開始 Twitch 重新授權')
    } finally {
      setBusyAction(null)
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

  const confirmRemoval = async () => {
    if (!activeTenant || !confirmation) return
    if (confirmation.kind === 'bot') {
      const account = confirmation.account
      setBusyAction(`remove:${account.platform_user_id}`)
      try {
        await unlinkBotAccount(activeTenant.channel_id, account.platform_user_id)
        setAccounts(current =>
          current.filter(item => item.platform_user_id !== account.platform_user_id)
        )
        setConfirmation(null)
        toast.success('已從這個頻道移除 Bot 帳號')
      } catch (error) {
        toastApiError(error, '移除 Bot 帳號失敗')
      } finally {
        setBusyAction(null)
      }
      return
    }

    setBusyAction('disconnect:broadcaster')
    try {
      await disconnectBroadcasterAuthorization(activeTenant.channel_id)
      toast.success('已停止 Niibot 並解除 Twitch 授權')
      window.location.href = '/login?reason=disconnected'
    } catch (error) {
      toastApiError(error, '解除 Twitch 授權失敗')
      setBusyAction(null)
    }
  }

  const openConfirmation = (target: ConfirmationTarget) => {
    setChannelConfirmation('')
    setConfirmation(target)
  }

  const isDisconnectConfirmed =
    confirmation?.kind === 'broadcaster' &&
    channelConfirmation.trim().toLowerCase() === broadcaster?.channel_name.toLowerCase()

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon="fa-brands fa-twitch" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle>Twitch 帳號與授權</CardTitle>
        </div>
        <CardDescription>管理 Twitch 實況主與聊天室發言帳號。</CardDescription>
      </CardHeader>

      <CardContent className="space-y-section">
        <section aria-labelledby="broadcaster-authorization-heading" className="space-y-3">
          <div>
            <h3 id="broadcaster-authorization-heading" className="font-semibold">
              實況主帳號
            </h3>
            <p className="mt-1 max-w-[70ch] text-sub text-muted-foreground">
              管理頻道與 Dashboard；解除後 Niibot 將停止服務。
            </p>
          </div>

          {broadcasterLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : broadcasterLoadFailed ? (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed p-section text-sub text-muted-foreground"
            >
              <span>實況主授權載入失敗。</span>
              <IconAction
                label="重新載入實況主授權"
                tooltip="重新載入"
                icon="fa-solid fa-rotate"
                onClick={() => void loadBroadcaster()}
              />
            </div>
          ) : broadcaster ? (
            <div className="space-y-3 rounded-lg bg-muted/45 p-3 sm:flex sm:items-center sm:justify-between sm:gap-4 sm:space-y-0">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {broadcaster.display_name || broadcaster.channel_name}
                  </span>
                  <AuthorizationBadge status={broadcaster.status} />
                  {!broadcaster.enabled && <Badge variant="outline">Niibot 已停止</Badge>}
                </div>
                <p className="text-label text-muted-foreground">@{broadcaster.channel_name}</p>
                <p className="mt-1 text-label text-muted-foreground">
                  {lastCheckedText(broadcaster.last_checked_at)}
                </p>
              </div>

              {canManage && (
                <div className="flex flex-wrap items-center gap-1">
                  <IconAction
                    label="重新檢查實況主授權"
                    tooltip="重新檢查"
                    icon="fa-solid fa-rotate"
                    busy={busyAction === 'check:broadcaster'}
                    disabled={busyAction !== null}
                    onClick={() => void checkBroadcaster()}
                  />
                  <IconAction
                    label="重新授權實況主帳號"
                    tooltip="重新授權"
                    icon="fa-solid fa-key"
                    busy={busyAction === 'reauthorize:broadcaster'}
                    disabled={busyAction !== null}
                    onClick={() => void reauthorizeBroadcaster()}
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => openConfirmation({ kind: 'broadcaster' })}
                    disabled={busyAction !== null}
                  >
                    解除授權
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-section text-sub text-muted-foreground">
              尚未找到實況主授權。
            </p>
          )}
        </section>

        <section
          aria-labelledby="bot-authorizations-heading"
          className="space-y-3 border-t pt-section"
        >
          <div>
            <h3 id="bot-authorizations-heading" className="font-semibold">
              聊天室發言帳號
            </h3>
            <p className="mt-1 max-w-[70ch] text-sub text-muted-foreground">
              Niibot 會選用其中一個帳號在聊天室發言。
            </p>
          </div>

          {accountsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : accountsLoadFailed ? (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed p-section text-sub text-muted-foreground"
            >
              <span>發言帳號載入失敗。</span>
              <IconAction
                label="重新載入聊天室發言帳號"
                tooltip="重新載入"
                icon="fa-solid fa-rotate"
                onClick={() => void loadAccounts()}
              />
            </div>
          ) : accounts.length === 0 ? (
            <p className="rounded-lg border border-dashed p-section text-sub text-muted-foreground">
              尚未設定可用的 Bot 帳號。
            </p>
          ) : (
            <ul className="space-y-2" aria-label="聊天室發言帳號">
              {accounts.map(account => (
                <li
                  key={account.platform_user_id}
                  className="space-y-3 rounded-lg border px-3 py-3 sm:flex sm:items-center sm:gap-3 sm:space-y-0"
                >
                  <div className="flex min-w-0 flex-1 items-center gap-3">
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
                        {account.is_system_default && <Badge variant="secondary">系統管理</Badge>}
                        {account.is_active && <Badge variant="outline">目前使用</Badge>}
                        <AuthorizationBadge status={account.authorization_status} />
                      </div>
                      <p className="truncate text-label text-muted-foreground">
                        @{account.login} · {lastCheckedText(account.last_checked_at)}
                      </p>
                    </div>
                  </div>

                  {canManage && (
                    <div className="flex flex-wrap items-center gap-1 sm:justify-end">
                      <IconAction
                        label={`重新檢查 ${account.display_name}`}
                        tooltip="重新檢查"
                        icon="fa-solid fa-rotate"
                        busy={busyAction === `check:${account.platform_user_id}`}
                        disabled={busyAction !== null}
                        onClick={() => void checkBot(account)}
                      />
                      {!account.is_system_default && (
                        <>
                          <IconAction
                            label={`重新授權 ${account.display_name}`}
                            tooltip="重新授權"
                            icon="fa-solid fa-key"
                            busy={busyAction === `reauthorize:${account.platform_user_id}`}
                            disabled={busyAction !== null}
                            onClick={() => void reauthorizeBot(account)}
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                            onClick={() => openConfirmation({ kind: 'bot', account })}
                            disabled={
                              busyAction !== null || account.is_active || account.is_desired
                            }
                            aria-label={`從這個頻道移除 ${account.display_name}`}
                            title={
                              account.is_active || account.is_desired
                                ? '請先改用其他 Bot'
                                : undefined
                            }
                          >
                            從這個頻道移除
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {canManage && (
          <section className="space-y-3 border-t pt-section" aria-labelledby="invite-bot-heading">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 id="invite-bot-heading" className="font-semibold">
                  邀請其他發言帳號
                </h3>
                <p className="mt-1 text-sub text-muted-foreground">
                  分享 30 分鐘有效的一次性連結。
                </p>
              </div>
              <Button size="sm" onClick={() => void createInvite()} disabled={busyAction !== null}>
                {busyAction === 'create-invite' ? (
                  <Spinner className="mr-2" />
                ) : (
                  <Icon icon="fa-solid fa-link" size="xs" />
                )}
                邀請帳號
              </Button>
            </div>

            {invite && (
              <div className="space-y-2 rounded-lg bg-muted/45 p-3">
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
                  <Input
                    className="min-w-0 flex-1"
                    value={invite.public_url}
                    readOnly
                    aria-label="Bot 邀請 URL"
                  />
                  <div className="flex shrink-0 gap-1">
                    <IconAction
                      label="複製邀請連結"
                      tooltip="複製連結"
                      icon="fa-solid fa-copy"
                      onClick={() => void copyInvite()}
                    />
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button size="icon-sm" variant="outline" asChild>
                          <a
                            href={invite.public_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label="開啟邀請連結"
                          >
                            <Icon icon="fa-solid fa-arrow-up-right-from-square" size="sm" />
                          </a>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>開啟連結</TooltipContent>
                    </Tooltip>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}
      </CardContent>

      <AlertDialog
        open={confirmation !== null}
        onOpenChange={open => {
          if (!open && busyAction === null) setConfirmation(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmation?.kind === 'bot'
                ? `從這個頻道移除「${confirmation.account.display_name}」？`
                : '停止 Niibot 並解除 Twitch 授權？'}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                {confirmation?.kind === 'bot' ? (
                  <ul className="list-disc space-y-1 pl-5">
                    <li>這個帳號會從目前頻道的發言帳號清單移除</li>
                    <li>其他頻道若仍在使用，授權會保留</li>
                    <li>既有設定與歷史紀錄不會刪除</li>
                  </ul>
                ) : (
                  <>
                    <ul className="list-disc space-y-1 pl-5">
                      <li>Niibot 會立即停止這個頻道的服務</li>
                      <li>你目前所有 Dashboard 登入會立即登出</li>
                      <li>設定與歷史紀錄會保留，之後重新授權仍可使用</li>
                    </ul>
                    <div className="space-y-2">
                      <label
                        htmlFor="channel-disconnect-confirmation"
                        className="block font-medium"
                      >
                        輸入 <span className="font-mono">{broadcaster?.channel_name}</span> 以確認
                      </label>
                      <Input
                        id="channel-disconnect-confirmation"
                        aria-label="輸入頻道帳號以確認"
                        value={channelConfirmation}
                        onChange={event => setChannelConfirmation(event.target.value)}
                        autoComplete="off"
                      />
                    </div>
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busyAction !== null}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={
                busyAction !== null ||
                (confirmation?.kind === 'broadcaster' && !isDisconnectConfirmed)
              }
              onClick={event => {
                event.preventDefault()
                void confirmRemoval()
              }}
            >
              {busyAction?.startsWith('remove:') || busyAction === 'disconnect:broadcaster' ? (
                <Spinner />
              ) : null}
              {confirmation?.kind === 'bot' ? '確認移除' : '確認停止並解除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

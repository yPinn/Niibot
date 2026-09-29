import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  type BotAccount,
  type BotAccountSelection,
  type BotInviteCreated,
  type BroadcasterAuthorization,
  checkBotAuthorization,
  checkBroadcasterAuthorization,
  createBotInvite,
  createBotReauthorizationInvite,
  disconnectBroadcasterAuthorization,
  getBotAccountSelection,
  getBotInviteStatus,
  getBroadcasterAuthorization,
  listBotAccounts,
  type TwitchAuthorizationStatus,
  unlinkBotAccount,
  updateBotAccountSelection,
} from '@/api/botAccounts'
import { openTwitchOAuth } from '@/api/twitchOAuth'
import { Icon, Spinner } from '@/components/primitives'
import { TwitchAccountIdentity } from '@/components/TwitchAccountIdentity'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { useTenant } from '@/contexts/TenantContext'
import { toastApiError } from '@/lib/toast-error'

type ConfirmationTarget = { kind: 'bot'; account: BotAccount } | { kind: 'broadcaster' } | null

const SYSTEM_SELECTION = '__system__'

const STATUS_COPY: Record<
  TwitchAuthorizationStatus,
  { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  valid: { label: '可使用', variant: 'secondary' },
  requires_reauthorization: { label: '需重新授權', variant: 'destructive' },
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

function selectionErrorCopy(errorCode: string | null, desiredName: string): string {
  if (errorCode === 'bot_not_moderator') {
    return `請先在 Twitch 將 ${desiredName} 設為頻道管理員，再重試。`
  }
  if (errorCode === 'bot_authorization_required' || errorCode === 'bot_scope_required') {
    return `請先重新授權 ${desiredName}，再重試。`
  }
  if (
    errorCode === 'broadcaster_authorization_required' ||
    errorCode === 'broadcaster_scope_required'
  ) {
    return '請先更新實況主授權，再重試。'
  }
  return '暫時無法切換，請稍後再試。'
}

export function BotAccountsCard() {
  const { activeTenant } = useTenant()
  const [accounts, setAccounts] = useState<BotAccount[]>([])
  const [broadcaster, setBroadcaster] = useState<BroadcasterAuthorization | null>(null)
  const [selection, setSelection] = useState<BotAccountSelection | null>(null)
  const [selectionChoice, setSelectionChoice] = useState(SYSTEM_SELECTION)
  const [accountsLoading, setAccountsLoading] = useState(false)
  const [broadcasterLoading, setBroadcasterLoading] = useState(false)
  const [selectionLoading, setSelectionLoading] = useState(false)
  const [accountsLoadFailed, setAccountsLoadFailed] = useState(false)
  const [broadcasterLoadFailed, setBroadcasterLoadFailed] = useState(false)
  const [selectionLoadFailed, setSelectionLoadFailed] = useState(false)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [invite, setInvite] = useState<BotInviteCreated | null>(null)
  const [inviteStatus, setInviteStatus] = useState<
    'pending' | 'authorized' | 'declined' | 'expired' | null
  >(null)
  const [confirmation, setConfirmation] = useState<ConfirmationTarget>(null)
  const [channelConfirmation, setChannelConfirmation] = useState('')
  const canManage = activeTenant?.capabilities.includes('manage_bot_accounts') ?? false
  const canSwitch = activeTenant?.capabilities.includes('switch_bot') ?? false

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

  const loadSelection = useCallback(async () => {
    if (!activeTenant) return
    setSelectionLoading(true)
    setSelectionLoadFailed(false)
    try {
      const next = await getBotAccountSelection(activeTenant.channel_id)
      setSelection(next)
      setSelectionChoice(next.desired_bot_user_id ?? SYSTEM_SELECTION)
    } catch {
      setSelectionLoadFailed(true)
    } finally {
      setSelectionLoading(false)
    }
  }, [activeTenant])

  const loadAuthorizations = useCallback(
    async () => Promise.allSettled([loadAccounts(), loadBroadcaster(), loadSelection()]),
    [loadAccounts, loadBroadcaster, loadSelection]
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

  useEffect(() => {
    if (!activeTenant || selection?.status !== 'switching') return
    const poll = async () => {
      try {
        const next = await getBotAccountSelection(activeTenant.channel_id)
        setSelection(next)
        setSelectionChoice(next.desired_bot_user_id ?? SYSTEM_SELECTION)
        if (next.status !== 'switching') await loadAccounts()
      } catch {
        // A later poll or manual retry can recover from a transient read failure.
      }
    }
    const intervalId = window.setInterval(() => void poll(), 2500)
    return () => window.clearInterval(intervalId)
  }, [activeTenant, loadAccounts, selection?.status])

  const createInvite = async () => {
    if (!activeTenant) return
    setBusyAction('create-invite')
    try {
      const created = await createBotInvite(activeTenant.channel_id)
      setInvite(created)
      setInviteStatus('pending')
    } catch (error) {
      toastApiError(error, '建立邀請失敗')
    } finally {
      setBusyAction(null)
    }
  }

  const applySelection = async () => {
    if (!activeTenant || !selection) return
    const botUserId = selectionChoice === SYSTEM_SELECTION ? null : selectionChoice
    setBusyAction('switch-bot')
    try {
      const next = await updateBotAccountSelection(activeTenant.channel_id, botUserId)
      setSelection(next)
      setSelectionChoice(next.desired_bot_user_id ?? SYSTEM_SELECTION)
      if (next.status === 'active') {
        await loadAccounts()
        toast.success('發言帳號已更新')
      }
    } catch (error) {
      toastApiError(error, '切換發言帳號失敗')
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
      toast.success(`已重新確認 ${account.display_name}`)
    } catch (error) {
      toastApiError(error, '重新檢查發言帳號失敗')
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
      toast.success('邀請連結已複製')
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
        toast.success('已從這個頻道移除發言帳號')
      } catch (error) {
        toastApiError(error, '移除發言帳號失敗')
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

  const systemAccount = accounts.find(account => account.is_system_default)
  const accountName = (botUserId: string | null) => {
    if (botUserId === null) return systemAccount?.display_name ?? 'Niibot 系統帳號'
    return (
      accounts.find(account => account.platform_user_id === botUserId)?.display_name ?? '已選帳號'
    )
  }
  const selectedBotUserId = selectionChoice === SYSTEM_SELECTION ? null : selectionChoice
  const selectionUnchanged = selection?.desired_bot_user_id === selectedBotUserId
  const selectionActionDisabled =
    busyAction !== null ||
    selectionLoading ||
    !selection ||
    selection.status === 'switching' ||
    (selectionUnchanged && selection.status !== 'failed')

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon="fa-brands fa-twitch" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle>Twitch 帳號</CardTitle>
        </div>
        <CardDescription>查看授權狀態並選擇發言帳號。</CardDescription>
      </CardHeader>

      <CardContent className="grid gap-card xl:grid-cols-[minmax(0,2fr)_minmax(20rem,1fr)]">
        <section
          aria-labelledby="broadcaster-authorization-heading"
          className="min-w-0 space-y-section"
        >
          <h3 id="broadcaster-authorization-heading" className="text-content font-semibold">
            實況主帳號
          </h3>

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
            <div className="bg-muted/45 flex flex-col gap-section rounded-lg p-section sm:flex-row sm:items-center sm:justify-between">
              <TwitchAccountIdentity
                className="flex-1"
                avatar={broadcaster.avatar}
                displayName={broadcaster.display_name || broadcaster.channel_name}
                login={broadcaster.channel_name}
                badges={
                  <>
                    <AuthorizationBadge status={broadcaster.status} />
                    {!broadcaster.enabled && <Badge variant="outline">Niibot 已停止</Badge>}
                  </>
                }
              />

              {canManage && (
                <div className="flex flex-wrap items-center gap-element sm:justify-end">
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

        <aside
          aria-labelledby="sender-account-heading"
          className="bg-muted/25 min-w-0 space-y-section rounded-lg border p-section"
        >
          <div className="flex items-center justify-between gap-element">
            <h3 id="sender-account-heading" className="text-content font-semibold">
              發言帳號
            </h3>
            {canManage && (
              <IconAction
                label="邀請發言帳號"
                tooltip="邀請發言帳號"
                icon="fa-solid fa-link"
                busy={busyAction === 'create-invite'}
                disabled={busyAction !== null}
                onClick={() => void createInvite()}
              />
            )}
          </div>

          {canSwitch &&
            (selectionLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : selectionLoadFailed ? (
              <div
                role="alert"
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed p-section text-sub text-muted-foreground"
              >
                <span>發言帳號選擇載入失敗。</span>
                <IconAction
                  label="重新載入發言帳號選擇"
                  tooltip="重新載入"
                  icon="fa-solid fa-rotate"
                  onClick={() => void loadSelection()}
                />
              </div>
            ) : selection ? (
              <section aria-label="選擇發言帳號" className="space-y-element border-b pb-section">
                <div className="flex items-end gap-element">
                  <div className="min-w-0 flex-1 space-y-element">
                    <span className="text-label font-medium">選擇發言帳號</span>
                    <Select
                      value={selectionChoice}
                      onValueChange={setSelectionChoice}
                      disabled={busyAction !== null || selection.status === 'switching'}
                    >
                      <SelectTrigger aria-label="選擇發言帳號" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {accounts.map(account => {
                          const sameIdentity = account.platform_user_id === activeTenant?.channel_id
                          const authorizationUnavailable =
                            account.authorization_status !== 'valid' || account.requires_reauth
                          return (
                            <SelectItem
                              key={account.platform_user_id}
                              value={
                                account.is_system_default
                                  ? SYSTEM_SELECTION
                                  : account.platform_user_id
                              }
                              disabled={sameIdentity || authorizationUnavailable}
                            >
                              {account.display_name}
                              {sameIdentity
                                ? '（不能使用頻道主帳號）'
                                : authorizationUnavailable
                                  ? '（需重新授權）'
                                  : ''}
                            </SelectItem>
                          )
                        })}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    aria-label="切換發言帳號"
                    disabled={selectionActionDisabled}
                    onClick={() => void applySelection()}
                  >
                    {busyAction === 'switch-bot' && <Spinner />}
                    {selection.status === 'failed' && selectionUnchanged ? '重試' : '切換'}
                  </Button>
                </div>

                <div role="status" aria-live="polite" className="text-label text-muted-foreground">
                  {selection.status === 'active' ? (
                    <span>
                      目前使用：
                      <strong className="font-medium text-foreground">
                        {accountName(selection.active_bot_user_id)}
                      </strong>
                    </span>
                  ) : selection.status === 'switching' ? (
                    <span>
                      正在切換至{' '}
                      <strong className="font-medium text-foreground">
                        {accountName(selection.desired_bot_user_id)}
                      </strong>
                      ；完成前仍使用 {accountName(selection.active_bot_user_id)}。
                    </span>
                  ) : (
                    <span>
                      切換未完成，仍使用 {accountName(selection.active_bot_user_id)}。
                      {selectionErrorCopy(
                        selection.error_code,
                        accountName(selection.desired_bot_user_id)
                      )}
                    </span>
                  )}
                </div>
              </section>
            ) : null)}

          <h4 className="text-label font-semibold">可用帳號</h4>

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
                label="重新載入發言帳號"
                tooltip="重新載入"
                icon="fa-solid fa-rotate"
                onClick={() => void loadAccounts()}
              />
            </div>
          ) : accounts.length === 0 ? (
            <p className="rounded-lg border border-dashed p-section text-sub text-muted-foreground">
              尚無可用的發言帳號。
            </p>
          ) : (
            <ul className="space-y-element" aria-label="可用發言帳號">
              {accounts.map(account => (
                <li
                  key={account.platform_user_id}
                  className="space-y-section rounded-lg border bg-card p-section"
                >
                  <TwitchAccountIdentity
                    avatar={account.avatar}
                    displayName={account.display_name}
                    login={account.login}
                    badges={
                      <>
                        {account.is_system_default && <Badge variant="secondary">系統帳號</Badge>}
                        <AuthorizationBadge status={account.authorization_status} />
                      </>
                    }
                  />

                  {canManage && (
                    <div className="flex flex-wrap items-center gap-element">
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
                          <IconAction
                            label={`從這個頻道移除 ${account.display_name}`}
                            tooltip={
                              account.is_active || account.is_desired
                                ? '請先改用其他帳號'
                                : '從此頻道移除'
                            }
                            icon="fa-solid fa-trash-can"
                            onClick={() => openConfirmation({ kind: 'bot', account })}
                            disabled={
                              busyAction !== null || account.is_active || account.is_desired
                            }
                          />
                        </>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {invite && (
            <section
              aria-label="邀請狀態"
              className="bg-card space-y-element rounded-lg border p-section"
            >
              <div className="flex items-center justify-between gap-element">
                <p className="text-label font-medium">
                  {inviteStatus === 'authorized'
                    ? '授權已完成'
                    : inviteStatus === 'pending'
                      ? '等待帳號持有人授權'
                      : '邀請已結束'}
                </p>
                <div className="flex items-center gap-element">
                  {inviteStatus === 'pending' && <Spinner />}
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
              {inviteStatus === 'pending' && (
                <p className="text-label text-muted-foreground">
                  連結 30 分鐘內有效，請交給帳號持有人。
                </p>
              )}
            </section>
          )}
        </aside>
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
                  <p>這個帳號將不再供目前頻道使用；其他頻道不受影響。</p>
                ) : (
                  <>
                    <p>Niibot 會停止此頻道的服務，你也會登出管理後台。設定與紀錄會保留。</p>
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

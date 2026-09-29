import { useSearchParams } from 'react-router-dom'

import { FadeIn, Icon } from '@/components/primitives'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useSensitivePageMetadata } from '@/hooks/useSensitivePageMetadata'

type FailureCopy = {
  description: string
  action: string
}

const DEFAULT_FAILURE: FailureCopy = {
  description: 'Bot 授權未完成，請重新取得授權連結。',
  action: '若仍無法完成，請通知 Niibot 管理員。',
}

const FAILURE_COPY: Record<string, FailureCopy> = {
  authorization_denied: {
    description: '你已取消 Twitch 授權。',
    action: '如需使用 Bot，請以新的授權連結重試。',
  },
  provider_unavailable: {
    description: 'Twitch 授權暫時無法使用。',
    action: '請稍後以新的授權連結重試。',
  },
  bot_invite_expired: {
    description: 'Bot 授權連結已失效。',
    action: '請向邀請人索取新的授權連結。',
  },
  bot_invite_already_used: {
    description: 'Bot 授權連結已失效。',
    action: '請向邀請人索取新的授權連結。',
  },
  bot_invite_wrong_account: {
    description: '請使用指定的 Bot 帳號完成授權。',
    action: '切換帳號後，請以新的授權連結重試。',
  },
  bot_account_missing_scopes: {
    description: 'Bot 權限未完整授予。',
    action: '請以新的授權連結重試並接受必要權限。',
  },
  bot_account_role_conflict: {
    description: '這個 Twitch 帳號已作為 Niibot 實況主使用。',
    action: '請改用另一個 Bot 帳號。',
  },
}

export default function BotAuthorizationResult() {
  useDocumentTitle('Bot 授權結果')
  useSensitivePageMetadata()
  const [params] = useSearchParams()
  const succeeded = params.get('status') === 'success'
  const failure = FAILURE_COPY[params.get('reason') ?? ''] ?? DEFAULT_FAILURE

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-page md:p-page-lg">
      <FadeIn className="w-full max-w-lg">
        <Card className="overflow-hidden">
          <CardHeader className="items-center justify-items-center gap-element text-center">
            <div
              className={`flex size-10 items-center justify-center rounded-full ${
                succeeded ? 'bg-status-online/10' : 'bg-destructive/10'
              }`}
            >
              <Icon
                icon={succeeded ? 'fa-solid fa-check' : 'fa-solid fa-xmark'}
                wrapperClassName={succeeded ? 'text-status-online' : 'text-destructive'}
              />
            </div>
            <h1 className="text-page-title font-bold">
              {succeeded ? 'Bot 授權完成' : 'Bot 授權未完成'}
            </h1>
            <CardDescription className="max-w-[48ch] text-balance">
              {succeeded ? '邀請人現在可以在自己的頻道選用這個 Bot 帳號。' : failure.description}
            </CardDescription>
          </CardHeader>
          <CardContent className="pb-card">
            <p className="text-center text-sub text-muted-foreground">
              {succeeded ? '你可以關閉這個頁面。' : failure.action}
            </p>
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  )
}

import { useSearchParams } from 'react-router-dom'

import { FadeIn, Icon } from '@/components/primitives'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function BotAuthorizationResult() {
  useDocumentTitle('Bot 授權結果')
  const [params] = useSearchParams()
  const succeeded = params.get('status') === 'success'

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
              {succeeded
                ? '加密憑證已安全回傳給 Niibot。'
                : '連結可能已過期、使用過，或 Twitch 權限不完整。'}
            </CardDescription>
          </CardHeader>
          <CardContent className="pb-card">
            <p className="text-center text-sub text-muted-foreground">
              {succeeded ? '你可以關閉這個頁面。' : '請向邀請人索取新的授權連結。'}
            </p>
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  )
}

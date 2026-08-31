import { useSearchParams } from 'react-router-dom'

import { Icon } from '@/components/primitives'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function BotAuthorizationResult() {
  useDocumentTitle('Bot 授權結果')
  const [params] = useSearchParams()
  const succeeded = params.get('status') === 'success'

  return (
    <main className="grid min-h-svh place-items-center bg-background px-4 py-10">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <div
            className={`mx-auto mb-2 grid size-12 place-items-center rounded-full ${
              succeeded
                ? 'bg-status-online/10 text-status-online'
                : 'bg-destructive/10 text-destructive'
            }`}
          >
            <Icon icon={succeeded ? 'fa-solid fa-check' : 'fa-solid fa-xmark'} size="lg" />
          </div>
          <h1 className="text-page-title font-semibold">
            {succeeded ? 'Bot 授權完成' : 'Bot 授權未完成'}
          </h1>
          <CardDescription>
            {succeeded
              ? '加密憑證已安全回傳給 Niibot。'
              : '連結可能已過期、使用過，或 Twitch 權限不完整。'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {succeeded ? '你可以關閉這個頁面。' : '請向邀請人索取新的授權連結。'}
          </p>
        </CardContent>
      </Card>
    </main>
  )
}

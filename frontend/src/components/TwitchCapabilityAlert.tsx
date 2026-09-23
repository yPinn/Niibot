import { toast } from 'sonner'

import type { TwitchCapability } from '@/api/botAccounts'
import { errorMessage } from '@/api/errors'
import { openTwitchOAuth } from '@/api/twitchOAuth'
import { Alert, AlertDescription, AlertTitle, Button } from '@/components/ui'

interface TwitchCapabilityAlertProps {
  capabilities: TwitchCapability[]
}

export function TwitchCapabilityAlert({ capabilities }: TwitchCapabilityAlertProps) {
  const unavailable = capabilities.filter(item => !item.available)
  if (unavailable.length === 0) return null

  const labels = unavailable.map(item => item.label).join('、')
  const startAuthorization = () => {
    void openTwitchOAuth().catch(error => {
      toast.error('無法啟動 Twitch 授權', {
        id: 'twitch-capability-oauth-failed',
        description: errorMessage(error, '登入服務暫時無法使用，請稍後再試'),
      })
    })
  }

  return (
    <Alert>
      <AlertTitle>部分 Twitch 功能尚未授權</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>{labels}目前保持鎖定，其他已授權功能不受影響。</span>
        <Button size="sm" variant="outline" onClick={startAuthorization}>
          更新 Twitch 授權
        </Button>
      </AlertDescription>
    </Alert>
  )
}

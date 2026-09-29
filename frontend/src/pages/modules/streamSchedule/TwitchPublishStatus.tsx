import type { StreamSchedulePublishStatus } from '@/api/streamSchedule'
import { Alert, AlertDescription, AlertTitle, Button } from '@/components/ui'

interface TwitchPublishStatusProps {
  value: StreamSchedulePublishStatus | null
  capabilityAvailable: boolean
  retrying: boolean
  onRetry: () => void
}

function errorMessage(code: string | null): string {
  switch (code) {
    case 'missing_scope':
    case 'unauthorized':
      return '需要更新 Twitch 授權後才能同步。'
    case 'non_recurring_unsupported':
      return '單次行程僅支援 Twitch Affiliate／Partner 頻道。'
    case 'invalid_request':
    case 'invalid_local_state':
      return '部分排程內容無法發布，請檢查時間、標題與分類。'
    default:
      return 'Twitch 暫時無法同步，請稍後重試。'
  }
}

export function TwitchPublishStatus({
  value,
  capabilityAvailable,
  retrying,
  onRetry,
}: TwitchPublishStatusProps) {
  if (!value || value.status === 'idle') return null
  if (!capabilityAvailable && value.last_error_code === 'missing_scope') return null
  if (value.status === 'synced') {
    return (
      <p className="text-muted-foreground text-xs" aria-live="polite">
        已同步至 Twitch 行程表
      </p>
    )
  }
  if (value.status === 'pending') {
    return (
      <Alert>
        <AlertTitle>正在同步 Twitch 行程表</AlertTitle>
        <AlertDescription>本地排程已儲存，可繼續編輯。</AlertDescription>
      </Alert>
    )
  }

  const canRetry = value.status === 'error' || value.last_error_code == null
  return (
    <Alert variant={value.status === 'error' ? 'destructive' : 'default'}>
      <AlertTitle>Twitch 行程表尚未同步</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>{errorMessage(value.last_error_code)}</span>
        {canRetry && (
          <Button size="sm" variant="outline" disabled={retrying} onClick={onRetry}>
            {retrying ? '同步中…' : '重新同步'}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}

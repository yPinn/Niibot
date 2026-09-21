import type { CheckinLeaderboardEntry } from '@/api/checkin'
import { EmptyState, Icon } from '@/components/primitives'
import { Alert, AlertDescription, AlertTitle, Badge, Button, Skeleton } from '@/components/ui'

interface CheckinLeaderboardProps {
  entries: readonly CheckinLeaderboardEntry[]
  loading: boolean
  loadFailed: boolean
  onRetry: () => void
}

export function CheckinLeaderboard({
  entries,
  loading,
  loadFailed,
  onRetry,
}: CheckinLeaderboardProps) {
  return (
    <section className="space-y-3" aria-labelledby="checkin-leaderboard-title">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 id="checkin-leaderboard-title" className="font-semibold">
            簽到排行榜
          </h3>
          <p className="text-label text-muted-foreground">依累積簽到天數排序，顯示前 100 名。</p>
        </div>
        {!loading && !loadFailed && entries.length > 0 && (
          <Badge variant="secondary" className="tabular-nums">
            {entries.length} 位
          </Badge>
        )}
      </div>

      {loading ? (
        <div className="space-y-2" aria-label="簽到排行榜載入中">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-16 w-full" />
          ))}
        </div>
      ) : loadFailed ? (
        <Alert variant="destructive">
          <Icon icon="fa-solid fa-circle-exclamation" />
          <AlertTitle>簽到排行榜載入失敗</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>設定仍可正常編輯；請稍後重新載入排行榜。</p>
            <Button size="sm" variant="outline" onClick={onRetry}>
              重新載入排行榜
            </Button>
          </AlertDescription>
        </Alert>
      ) : entries.length === 0 ? (
        <EmptyState
          icon="fa-solid fa-calendar-check"
          title="尚無簽到紀錄"
          description="觀眾完成第一次簽到後，就會出現在這裡。"
        />
      ) : (
        <ol className="divide-y rounded-md border">
          {entries.map(entry => {
            const displayName = entry.display_name || entry.username
            const showHandle =
              entry.display_name !== null &&
              entry.display_name.localeCompare(entry.username, undefined, {
                sensitivity: 'accent',
              }) !== 0
            const rankColor =
              entry.rank === 1
                ? 'text-rank-gold'
                : entry.rank === 2
                  ? 'text-rank-silver'
                  : entry.rank === 3
                    ? 'text-rank-bronze'
                    : 'text-muted-foreground'
            return (
              <li
                key={entry.user_id}
                className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 px-3 py-3"
              >
                <span
                  className={`text-center text-sub font-semibold tabular-nums ${rankColor}`}
                  aria-label={`第 ${entry.rank} 名`}
                >
                  #{entry.rank}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sub font-medium">{displayName}</p>
                  <p className="mt-0.5 truncate text-label text-muted-foreground">
                    {showHandle && <>@{entry.username} · </>}最後簽到{' '}
                    <time dateTime={entry.last_checkin_date}>{entry.last_checkin_date}</time>
                  </p>
                </div>
                <p className="whitespace-nowrap text-sub font-semibold tabular-nums">
                  {entry.total_days.toLocaleString()} 天
                </p>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

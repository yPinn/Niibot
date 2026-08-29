import type { PlusProgramEstimate } from '@/api/analytics'
import { Icon, Spinner } from '@/components/primitives'
import { Skeleton } from '@/components/ui'
import { formatRelativeTime } from '@/lib/format'
import { PLUS_TIER2_POINTS, plusProgress } from '@/lib/plus-program'
import { cn } from '@/lib/utils'

interface PlusProgramCardProps {
  estimate: PlusProgramEstimate | null
  loading: boolean
  refreshing: boolean
  onRefresh: () => void
}

function splitColor(split: string): string {
  if (split === '70/30') return 'text-status-online'
  if (split === '60/40') return 'text-status-info'
  return 'text-muted-foreground'
}

const barPct = (points: number) => Math.min(100, Math.max(0, (points / PLUS_TIER2_POINTS) * 100))

export function PlusProgramCard({
  estimate,
  loading,
  refreshing,
  onRefresh,
}: PlusProgramCardProps) {
  if (loading) return <Skeleton className="h-32 rounded-md shrink-0" />
  if (!estimate) return null

  const { confirmed_points, confirmed_subs, pending_points, pending_subs, data_as_of } = estimate
  const prog = plusProgress(confirmed_points)
  const confirmedWidth = barPct(confirmed_points)
  const pendingWidth = Math.max(0, barPct(confirmed_points + pending_points) - confirmedWidth)

  return (
    <div className="rounded-md border px-2.5 py-2 flex flex-col gap-2 shrink-0">
      <div className="flex items-center justify-between">
        <p className="text-label text-muted-foreground">加強版方案積分（本月試算）</p>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="text-label text-muted-foreground hover:text-foreground inline-flex items-center gap-1 disabled:opacity-50"
        >
          {refreshing ? (
            <Spinner className="size-3" />
          ) : (
            <Icon icon="fa-solid fa-rotate" size="xs" />
          )}
          重新整理訂閱資料
        </button>
      </div>

      <div className="flex items-baseline gap-2">
        <span className={cn('text-card-title font-bold tabular-nums', splitColor(prog.split))}>
          {confirmed_points.toLocaleString()}
        </span>
        <span className="text-label text-muted-foreground">點 · 目前 {prog.split}</span>
      </div>

      <div
        className="h-1.5 w-full flex rounded-full bg-muted overflow-hidden"
        role="progressbar"
        aria-valuenow={confirmed_points}
        aria-valuemin={0}
        aria-valuemax={PLUS_TIER2_POINTS}
      >
        <div className="bg-primary" style={{ width: `${confirmedWidth}%` }} />
        <div className="bg-primary/30" style={{ width: `${pendingWidth}%` }} />
      </div>

      <p className="text-label text-muted-foreground">
        確認付費 {confirmed_subs} 位 · 待確認 {pending_subs} 位（最多 +{pending_points} 點）
      </p>
      <p className="text-label text-muted-foreground">
        {prog.nextThreshold === null
          ? '已達最高分潤級距'
          : `距 ${prog.nextThreshold === 100 ? '60/40' : '70/30'} 還差 ${prog.remaining} 點`}
      </p>

      {data_as_of && (
        <p className="text-label text-muted-foreground/60">
          訂閱資料更新於 {formatRelativeTime(data_as_of)}
        </p>
      )}
      <p className="text-label text-muted-foreground/60">
        Prime 與贈禮訂閱不計入積分；待確認的訂閱來源會在其續訂時判定。連續 3 個月達標未追蹤。
      </p>
    </div>
  )
}

import type { PlusProgramEstimate } from '@/api/analytics'
import { AffiliateLockOverlay } from '@/components/AffiliateLockOverlay'
import { Icon } from '@/components/primitives'
import { Button, Skeleton, Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { formatRelativeTime } from '@/lib/format'
import { PLUS_TIER2_POINTS, plusProgress, subsToClose } from '@/lib/plus-program'
import { cn } from '@/lib/utils'

interface PlusProgramCardProps {
  estimate: PlusProgramEstimate | null
  loading: boolean
  refreshing: boolean
  locked: boolean
  onRefresh: () => void
}

function splitColor(split: string): string {
  if (split === '70/30') return 'text-status-online'
  if (split === '60/40') return 'text-status-info'
  return 'text-muted-foreground'
}

/** Twitch calls the plan tiers 等級 1 / 等級 2; 50/50 is the un-qualified default. */
function planLabel(split: string): string {
  if (split === '70/30') return '等級 2（70/30）'
  if (split === '60/40') return '等級 1（60/40）'
  return '尚未達標（50/50）'
}

const barPct = (points: number) => Math.min(100, Math.max(0, (points / PLUS_TIER2_POINTS) * 100))

function CardShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative rounded-md border px-2.5 py-2 flex flex-col gap-2 shrink-0 overflow-hidden">
      {children}
    </div>
  )
}

export function PlusProgramCard({
  estimate,
  loading,
  refreshing,
  locked,
  onRefresh,
}: PlusProgramCardProps) {
  if (locked) {
    return (
      <CardShell>
        <AffiliateLockOverlay message="取得實況盟友資格後可查看" className="rounded-[inherit]" />
        <p className="text-label text-muted-foreground">加強版方案積分（試算）</p>
        <p className="text-card-title font-bold text-muted-foreground/40">—</p>
      </CardShell>
    )
  }
  if (loading) return <Skeleton className="h-36 rounded-md shrink-0" />
  if (!estimate) return null

  const { confirmed_points, confirmed_subs, pending_points, pending_subs, data_as_of } = estimate
  const prog = plusProgress(confirmed_points)
  const gap = subsToClose(prog.remaining)
  const nextTierLabel = prog.nextThreshold === 100 ? '等級 1（60/40）' : '等級 2（70/30）'
  const confirmedWidth = barPct(confirmed_points)
  const pendingWidth = Math.max(0, barPct(confirmed_points + pending_points) - confirmedWidth)

  return (
    <CardShell>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <p className="text-label text-muted-foreground">加強版方案積分（試算）</p>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex cursor-help">
                <Icon
                  icon="fa-solid fa-circle-info"
                  size="xs"
                  wrapperClassName="text-muted-foreground/50"
                />
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-60 text-label leading-relaxed">
              層級 1／2／3 訂閱各得 1／2／6 點，Prime
              與贈禮訂閱不計入。尚未確認來源的訂閱會在下次續訂時補上。取得資格另需連續 3 個月達標。
            </TooltipContent>
          </Tooltip>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="重新整理訂閱資料"
              onClick={onRefresh}
              disabled={refreshing}
              className="text-muted-foreground"
            >
              <Icon
                icon="fa-solid fa-rotate"
                size="2xs"
                className={cn(refreshing && 'animate-spin')}
              />
            </Button>
          </TooltipTrigger>
          <TooltipContent>重新整理訂閱資料</TooltipContent>
        </Tooltip>
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className={cn('text-card-title font-bold tabular-nums', splitColor(prog.split))}>
          {confirmed_points.toLocaleString()}
        </span>
        <span className="text-label text-muted-foreground">點</span>
        <span className="text-label text-muted-foreground ml-auto">{planLabel(prog.split)}</span>
      </div>

      <div className="flex flex-col gap-1">
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
          {`已確認 ${confirmed_subs} 位付費訂閱`}
          {pending_subs > 0 && `，另 ${pending_subs} 位待確認來源（最高再 +${pending_points} 點）`}
        </p>
      </div>

      {prog.nextThreshold === null ? (
        <p className="text-label text-status-online">已達等級 2（70/30）</p>
      ) : (
        <div className="flex flex-col gap-1">
          <p className="text-label text-muted-foreground tabular-nums">
            {`距 ${nextTierLabel} 還差 ${gap.points} 點`}
          </p>
          <div className="grid grid-cols-3 gap-1 text-label text-muted-foreground/70 tabular-nums">
            <span>{`層級 1 ×${gap.t1}`}</span>
            <span>{`層級 2 ×${gap.t2}`}</span>
            <span>{`層級 3 ×${gap.t3}`}</span>
          </div>
        </div>
      )}

      {data_as_of && (
        <p className="text-label text-muted-foreground/50">
          更新於 {formatRelativeTime(data_as_of)}
        </p>
      )}
    </CardShell>
  )
}

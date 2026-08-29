import { Icon } from '@/components/primitives'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Empty,
  EmptyTitle,
  Skeleton,
} from '@/components/ui'

interface StatItem {
  label: string
  value: number | string
}

interface StatsCardProps {
  title: string
  icon?: string
  items: StatItem[]
  loading?: boolean
  className?: string
}

export default function StatsCard({
  title,
  icon,
  items,
  loading = false,
  className = '',
}: StatsCardProps) {
  return (
    <Card className={`flex flex-col ${className}`}>
      <CardHeader className="shrink-0">
        <CardTitle className="flex items-center gap-element text-card-title">
          {icon && <Icon icon={icon} size="lg" wrapperClassName="text-primary" />}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-hidden pb-card">
        {loading ? (
          <div className="space-y-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full rounded-md" />
            ))}
          </div>
        ) : items.length > 0 ? (
          <div className="space-y-1 h-full overflow-y-auto">
            {items.map(item => (
              <div
                key={item.label}
                className="flex items-center justify-between rounded-md border bg-card p-2.5 hover:bg-accent transition-colors"
              >
                <span className="text-sub font-medium truncate flex-1 mr-2">{item.label}</span>
                <span className="text-sub font-bold text-primary tabular-nums">{item.value}</span>
              </div>
            ))}
          </div>
        ) : (
          <Empty className="border-none p-4">
            <EmptyTitle className="text-sub font-normal text-muted-foreground">暫無資料</EmptyTitle>
          </Empty>
        )}
      </CardContent>
    </Card>
  )
}

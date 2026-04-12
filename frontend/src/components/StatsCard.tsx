import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Empty,
  EmptyDescription,
  Icon,
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
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          {icon && <Icon icon={icon} wrapperClassName="size-5 text-primary" />}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-hidden pb-6">
        {loading ? (
          <div className="space-y-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full rounded-md" />
            ))}
          </div>
        ) : items.length > 0 ? (
          <div className="space-y-1 h-full overflow-y-auto">
            {items.map((item, index) => (
              <div
                key={index}
                className="flex items-center justify-between rounded-md border bg-card p-2.5 hover:bg-accent transition-colors"
              >
                <span className="text-sm font-medium truncate flex-1 mr-2">{item.label}</span>
                <span className="text-sm font-bold text-primary tabular-nums">{item.value}</span>
              </div>
            ))}
          </div>
        ) : (
          <Empty className="border-none p-4">
            <EmptyDescription>No data available</EmptyDescription>
          </Empty>
        )}
      </CardContent>
    </Card>
  )
}

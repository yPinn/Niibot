import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import { Card, CardContent, CardHeader, Separator, Skeleton } from '@/components/ui'

function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <Card className="h-full">
      <CardHeader>
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-4 w-48 max-w-full" />
      </CardHeader>
      <CardContent className="flex flex-col gap-card">
        {Array.from({ length: rows }, (_, index) => (
          <Skeleton key={index} className="h-14 w-full rounded-lg" />
        ))}
      </CardContent>
    </Card>
  )
}

export function VideoQueuePageSkeleton() {
  return (
    <>
      <Skeleton className="h-52 w-full rounded-xl" />

      <div
        data-layout="video-queue-row"
        className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch"
      >
        <div className="min-w-0 lg:col-span-8">
          <Card className="h-full min-h-120">
            <CardHeader>
              <Skeleton className="h-9 w-44" />
            </CardHeader>
            <CardContent className="flex flex-col gap-card">
              <Skeleton className="h-9 w-full" />
              <TableSkeletonRows count={7} />
            </CardContent>
          </Card>
        </div>
        <div className="min-w-0 lg:col-span-4">
          <CardSkeleton rows={3} />
        </div>
      </div>

      <Separator />

      <div
        data-layout="video-queue-row"
        className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch"
      >
        <div className="min-w-0 lg:col-span-8">
          <CardSkeleton rows={4} />
        </div>
        <div className="min-w-0 lg:col-span-4">
          <CardSkeleton rows={3} />
        </div>
      </div>
    </>
  )
}

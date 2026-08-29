import { Skeleton } from '@/components/ui'

/** The `Array.from({ length }).map(<Skeleton className="h-10 w-full" />)` loading
 * placeholder that every sortable-table card renders while fetching. */
export function TableSkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

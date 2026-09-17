import { Skeleton } from '@/components/ui'

// Mirrors CrosshairCardBase's real shape (header row, centered preview,
// footer row) — a plain aspect-square skeleton undercounts the card's real
// height and causes a visible jump when it resolves to real cards.
export function CrosshairCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border bg-muted py-element">
      <div className="flex items-center justify-between px-element">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="size-7 rounded-md" />
      </div>
      <div className="flex justify-center py-element">
        <Skeleton className="aspect-square w-2/3 rounded-lg" />
      </div>
      <div className="flex items-center justify-between px-element">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-6" />
      </div>
    </div>
  )
}

import { memo, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  type Crosshair,
  CROSSHAIR_GAME_LABELS,
  getPublicCrosshairs,
  type PublicChannelProfile,
} from '@/api/crosshairs'
import avatarFallback from '@/assets/images/Avatar.png'
import { CrosshairCardBase } from '@/components/crosshairs/CrosshairCardBase'
import { CrosshairDetailPreview } from '@/components/crosshairs/CrosshairPreview'
import { SortDropdown } from '@/components/crosshairs/SortDropdown'
import { copyCode } from '@/components/crosshairs/utils'
import { useTheme } from '@/components/theme-provider'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  FadeIn,
  Icon,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetSection,
  SheetTitle,
  Skeleton,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

type SortKey = 'default' | 'copies'

export default function CrosshairRepo() {
  const { username } = useParams<{ username: string }>()
  const { resolvedTheme, setTheme } = useTheme()

  const [crosshairs, setCrosshairs] = useState<Crosshair[]>([])
  const [channel, setChannel] = useState<PublicChannelProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Crosshair | null>(null)
  const [sort, setSort] = useState<SortKey>('copies')

  const displayName = channel?.display_name ?? username ?? ''
  useDocumentTitle(channel ? `${displayName}'s Crosshairs` : 'Crosshairs')

  useEffect(() => {
    if (!username) return
    let cancelled = false
    getPublicCrosshairs(username)
      .then(data => {
        if (!cancelled) {
          setChannel(data.channel)
          setCrosshairs(data.crosshairs)
        }
      })
      .catch(() => {
        if (!cancelled) setError('找不到該頻道或無法載入準星資料')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [username])

  const sorted = useMemo(() => {
    if (sort === 'copies') return [...crosshairs].sort((a, b) => b.copy_count - a.copy_count)
    return [...crosshairs].sort((a, b) => a.display_order - b.display_order)
  }, [crosshairs, sort])

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background px-page py-12">
      <Button variant="ghost" size="icon" className="absolute left-4 top-4" asChild>
        <Link to="/">
          <Icon icon="fa-solid fa-house" wrapperClassName="" />
        </Link>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-4 top-4"
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>

      <div className="w-full max-w-2xl">
        {loading ? (
          <Card className="rounded-2xl border shadow-xl">
            <CardHeader>
              <div className="flex flex-col items-center gap-3">
                <Skeleton className="h-24 w-24 rounded-full" />
                <Skeleton className="h-6 w-44" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between px-1 mb-card">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-7 w-7 rounded-md" />
              </div>
              <div className="grid grid-cols-1 gap-section sm:grid-cols-3">
                {Array.from({ length: 9 }).map((_, i) => (
                  <Skeleton key={i} className="aspect-square rounded-xl" />
                ))}
              </div>
            </CardContent>
          </Card>
        ) : error ? (
          <div className="flex items-center justify-center py-24 text-destructive">{error}</div>
        ) : (
          <FadeIn>
            <Card className="rounded-2xl border shadow-xl">
              <CardHeader>
                <div className="flex flex-col items-center">
                  <a
                    href={`https://twitch.tv/${username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group relative mb-4 select-none"
                  >
                    <Avatar className="h-24 w-24 border-4 border-primary shadow-lg">
                      <AvatarImage
                        src={channel?.profile_image_url ?? undefined}
                        alt={`${displayName} avatar`}
                      />
                      <AvatarFallback>
                        <img src={avatarFallback} alt="預設頭像" className="h-full w-full" />
                      </AvatarFallback>
                    </Avatar>
                    <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
                      <Icon
                        icon="fa-brands fa-twitch"
                        className="text-white"
                        wrapperClassName="size-8"
                      />
                    </div>
                  </a>
                  <CardTitle className="text-center text-page-title select-none">
                    {displayName}'s Crosshairs
                  </CardTitle>
                </div>
              </CardHeader>

              <CardContent>
                {crosshairs.length === 0 ? (
                  <EmptyState
                    icon="fa-solid fa-crosshairs"
                    title="尚無準星"
                    description="此實況主尚未公開分享任何準星"
                  />
                ) : (
                  <>
                    <div className="flex items-center justify-between px-1 mb-card">
                      <p className="flex items-center gap-2 text-sub text-muted-foreground select-none">
                        <Icon icon="fa-solid fa-crosshairs" wrapperClassName="size-3" />
                        {crosshairs.length} 個準星
                      </p>
                      <SortDropdown
                        value={sort}
                        onChange={setSort}
                        options={[
                          { value: 'copies', label: '複製次數', icon: 'fa-solid fa-copy' },
                          { value: 'default', label: '預設排序', icon: 'fa-solid fa-list' },
                        ]}
                      />
                    </div>
                    <div className="grid grid-cols-1 gap-section sm:grid-cols-3">
                      {sorted.map(c => (
                        <CrosshairCard key={c.id} crosshair={c} onSelect={setSelected} />
                      ))}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </FadeIn>
        )}
      </div>

      <Sheet open={!!selected} onOpenChange={open => !open && setSelected(null)}>
        <SheetContent side="right" className="sm:max-w-md">
          {selected && (
            <>
              <SheetHeader>
                <div className="flex items-center gap-element">
                  <Badge variant="secondary">{CROSSHAIR_GAME_LABELS[selected.game]}</Badge>
                </div>
                <SheetTitle className="mt-1">{selected.name}</SheetTitle>
              </SheetHeader>

              <SheetSection>
                <CrosshairDetailPreview game={selected.game} code={selected.code} />
              </SheetSection>

              <SheetSection title="準星代碼">
                <div className="flex items-center gap-element">
                  <code className="flex-1 break-all rounded bg-muted px-3 py-2 font-mono text-sub">
                    {selected.code}
                  </code>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => copyCode(selected.code, selected.id)}
                    title="複製代碼"
                  >
                    <Icon icon="fa-solid fa-copy" wrapperClassName="size-4" />
                  </Button>
                </div>
              </SheetSection>

              {selected.description && (
                <SheetSection title="備註">
                  <p className="text-sub text-muted-foreground">{selected.description}</p>
                </SheetSection>
              )}
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}

const CrosshairCard = memo(function CrosshairCard({
  crosshair,
  onSelect,
}: {
  crosshair: Crosshair
  onSelect: (c: Crosshair) => void
}) {
  return (
    <CrosshairCardBase
      crosshair={crosshair}
      onCopy={code => copyCode(code, crosshair.id)}
      onCardClick={() => onSelect(crosshair)}
      copyCount={crosshair.copy_count}
    />
  )
})

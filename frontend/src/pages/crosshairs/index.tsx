import { memo, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  type Crosshair,
  CROSSHAIR_GAME_LABELS,
  type CrosshairGame,
  getPublicCrosshairs,
  type PublicChannelProfile,
  recordCrosshairCopy,
} from '@/api/crosshairs'
import avatarFallback from '@/assets/images/Avatar.png'
import { useTheme } from '@/components/theme-provider'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Button,
  FadeIn,
  Icon,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetSection,
  SheetTitle,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { copyToClipboard } from '@/lib/clipboard'

import { CrosshairCardBase } from '../modules/crosshairs/CrosshairCardBase'
import { CrosshairDetailPreview } from '../modules/crosshairs/CrosshairPreview'

const GAME_LABELS: Record<string, string> = { all: 'All', ...CROSSHAIR_GAME_LABELS }

const GAME_TABS = ['all', 'valorant'] as const

function copyCode(code: string, id?: string) {
  copyToClipboard(code, '已複製準星代碼')
  if (id) recordCrosshairCopy(id)
}

export default function CrosshairRepo() {
  const { username } = useParams<{ username: string }>()
  const { resolvedTheme, setTheme } = useTheme()

  const [crosshairs, setCrosshairs] = useState<Crosshair[]>([])
  const [channel, setChannel] = useState<PublicChannelProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<string>('all')
  const [selected, setSelected] = useState<Crosshair | null>(null)

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

  const filtered = useMemo(
    () => (activeTab === 'all' ? crosshairs : crosshairs.filter(c => c.game === activeTab)),
    [crosshairs, activeTab]
  )

  // Only show tabs that have entries (or 'all')
  const activeTabs = useMemo(() => {
    const games = new Set(crosshairs.map(c => c.game))
    return GAME_TABS.filter(t => t === 'all' || games.has(t as CrosshairGame))
  }, [crosshairs])

  return (
    <div className="relative flex min-h-screen flex-col items-center bg-background px-page py-12">
      {/* Nav buttons */}
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

      <div className="w-full max-w-4xl">
        {loading ? (
          <div className="space-y-card">
            <div className="flex flex-col items-center gap-3">
              <Skeleton className="h-24 w-24 rounded-full" />
              <Skeleton className="h-6 w-40" />
            </div>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="aspect-square rounded-xl" />
              ))}
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-24 text-destructive">{error}</div>
        ) : (
          <FadeIn>
            {/* Channel header */}
            <div className="mb-empty flex flex-col items-center gap-3">
              <a
                href={`https://twitch.tv/${username}`}
                target="_blank"
                rel="noopener noreferrer"
                className="group relative"
              >
                <Avatar className="h-24 w-24 border-4 border-primary shadow-lg">
                  <AvatarImage src={channel?.profile_image_url ?? undefined} />
                  <AvatarFallback>
                    <img src={avatarFallback} alt="avatar" />
                  </AvatarFallback>
                </Avatar>
              </a>
              <div className="text-center">
                <h1 className="text-2xl font-bold">{displayName}</h1>
                <p className="text-sm text-muted-foreground">準星收藏庫</p>
              </div>
            </div>

            {crosshairs.length === 0 ? (
              <p className="py-16 text-center text-muted-foreground">目前沒有任何準星</p>
            ) : (
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="mb-card">
                  {activeTabs.map(tab => (
                    <TabsTrigger key={tab} value={tab}>
                      {GAME_LABELS[tab]}
                    </TabsTrigger>
                  ))}
                </TabsList>

                {activeTabs.map(tab => (
                  <TabsContent key={tab} value={tab}>
                    {filtered.length === 0 ? (
                      <p className="py-12 text-center text-muted-foreground">此遊戲尚無準星</p>
                    ) : (
                      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                        {filtered.map(c => (
                          <CrosshairCard key={c.id} crosshair={c} onSelect={setSelected} />
                        ))}
                      </div>
                    )}
                  </TabsContent>
                ))}
              </Tabs>
            )}
          </FadeIn>
        )}
      </div>

      {/* Detail sheet */}
      <Sheet open={!!selected} onOpenChange={open => !open && setSelected(null)}>
        <SheetContent side="right" className="sm:max-w-md">
          {selected && (
            <>
              <SheetHeader>
                <div className="flex items-center gap-element">
                  <Badge variant="secondary">{GAME_LABELS[selected.game]}</Badge>
                </div>
                <SheetTitle className="mt-1">{selected.name}</SheetTitle>
              </SheetHeader>

              <SheetSection>
                <CrosshairDetailPreview game={selected.game} code={selected.code} />
              </SheetSection>

              <SheetSection title="準星代碼">
                <div className="flex items-center gap-element">
                  <code className="flex-1 break-all rounded bg-muted px-3 py-2 font-mono text-sm">
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
                  <p className="text-sm text-muted-foreground">{selected.description}</p>
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
    />
  )
})

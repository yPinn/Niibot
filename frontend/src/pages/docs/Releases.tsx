import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import { getReleases, type GithubRelease } from '@/api/releases'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  Calendar,
  CalendarDayButton,
  Card,
  CardContent,
  CardHeader,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  Icon,
  Skeleton,
  Stagger,
  StaggerItem,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'

type MarkdownBlock =
  | { type: 'h2'; text: string }
  | { type: 'h3'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'p'; text: string }

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('zh-TW', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(iso))
}

function parseInline(text: string): ReactNode {
  const pattern = /\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)/g
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  let key = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }
    if (match[1] !== undefined) {
      nodes.push(
        <strong key={key++} className="font-semibold text-foreground">
          {match[1]}
        </strong>
      )
    } else if (match[2] !== undefined) {
      nodes.push(
        <code key={key++} className="rounded bg-muted px-1 py-0.5 font-mono text-label">
          {match[2]}
        </code>
      )
    } else if (match[3] !== undefined && match[4] !== undefined) {
      nodes.push(
        <a
          key={key++}
          href={match[4]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary underline-offset-4 hover:underline"
        >
          {match[3]}
        </a>
      )
    }
    lastIndex = pattern.lastIndex
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  if (nodes.length === 0) return text
  if (nodes.length === 1) return nodes[0]
  return <>{nodes}</>
}

function parseMarkdownBlocks(body: string): MarkdownBlock[] {
  return body.split('\n').reduce<MarkdownBlock[]>((acc, line) => {
    const h2 = line.match(/^## (.+)/)
    const h3 = line.match(/^### (.+)/)
    const li = line.match(/^[-*] (.+)/)

    if (h2) return [...acc, { type: 'h2', text: h2[1] }]
    if (h3) return [...acc, { type: 'h3', text: h3[1] }]
    if (li) {
      const last = acc[acc.length - 1]
      if (last?.type === 'ul') {
        return [...acc.slice(0, -1), { type: 'ul', items: [...last.items, li[1]] }]
      }
      return [...acc, { type: 'ul', items: [li[1]] }]
    }
    if (line.trim()) return [...acc, { type: 'p', text: line.trim() }]
    return acc
  }, [])
}

function ReleaseBody({ body }: { body: string }) {
  const blocks = parseMarkdownBlocks(body)

  return (
    <div className="flex flex-col gap-element">
      {blocks.map((block, i) => {
        if (block.type === 'h2') {
          return (
            <h2 key={i} className="text-card-title font-semibold text-foreground">
              {parseInline(block.text)}
            </h2>
          )
        }
        if (block.type === 'h3') {
          return (
            <h3 key={i} className="pl-element text-sub font-semibold text-muted-foreground">
              {parseInline(block.text)}
            </h3>
          )
        }
        if (block.type === 'ul') {
          return (
            <ul key={i} className="flex flex-col gap-1 pl-page">
              {block.items.map((item, j) => (
                <li key={j} className="flex gap-element">
                  <span className="mt-element size-1.5 shrink-0 rounded-full bg-muted-foreground/40" />
                  <span className="text-sub leading-relaxed text-foreground">
                    {parseInline(item)}
                  </span>
                </li>
              ))}
            </ul>
          )
        }
        return (
          <p key={i} className="text-sub leading-relaxed text-muted-foreground">
            {parseInline(block.text)}
          </p>
        )
      })}
    </div>
  )
}

function ReleaseCard({ release }: { release: GithubRelease }) {
  const displayName = release.name && release.name !== release.tag_name ? release.name : null

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-element">
          <Icon icon="fa-solid fa-tag" size="md" wrapperClassName="text-primary" />
          <span className="text-section-title font-bold">{release.tag_name}</span>
          {release.prerelease && (
            <Badge
              variant="secondary"
              className="border-status-warning/30 text-label text-status-warning"
            >
              Pre-release
            </Badge>
          )}
          <span className="ml-auto text-sub text-muted-foreground">
            {formatDate(release.published_at)}
          </span>
        </div>
        {displayName && <p className="text-sub text-muted-foreground">{displayName}</p>}
      </CardHeader>

      <CardContent>
        {release.body?.trim() ? (
          <ReleaseBody body={release.body} />
        ) : (
          <p className="text-label text-muted-foreground">此版本無更新說明。</p>
        )}
      </CardContent>
    </Card>
  )
}

function ReleaseSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-element">
          <Skeleton className="size-5 rounded" />
          <Skeleton className="h-5 w-20" />
          <Skeleton className="ml-auto h-4 w-24" />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-element">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </CardContent>
    </Card>
  )
}

const toDayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`

function ReleaseCalendar({
  releases,
  onSelect,
}: {
  releases: GithubRelease[]
  onSelect: (id: number) => void
}) {
  const { releaseByDay, defaultMonth } = useMemo(() => {
    const byDay = new Map<string, GithubRelease>()
    for (const r of releases) {
      const d = new Date(r.published_at)
      const key = toDayKey(d)
      if (!byDay.has(key)) {
        byDay.set(key, r)
      }
    }
    return {
      releaseByDay: byDay,
      defaultMonth: releases.length > 0 ? new Date(releases[0].published_at) : new Date(),
    }
  }, [releases])

  return (
    <Calendar
      mode="single"
      defaultMonth={defaultMonth}
      showOutsideDays={false}
      className="[--cell-size:--spacing(9)]"
      classNames={{
        month: 'flex w-full flex-col gap-2',
        week: 'mt-1 flex w-full',
      }}
      disabled={date => !releaseByDay.has(toDayKey(date))}
      onSelect={date => {
        if (!date) return
        const release = releaseByDay.get(toDayKey(date))
        if (release) onSelect(release.id)
      }}
      components={{
        DayButton: ({ day, modifiers, className, ...props }) => {
          const release = releaseByDay.get(toDayKey(day.date))
          if (release) {
            return (
              <Tooltip>
                <TooltipTrigger asChild>
                  <CalendarDayButton
                    day={day}
                    modifiers={modifiers}
                    className={cn(
                      className,
                      'bg-primary/15 text-primary hover:bg-primary hover:text-primary-foreground'
                    )}
                    {...props}
                  />
                </TooltipTrigger>
                <TooltipContent side="top">{release.tag_name}</TooltipContent>
              </Tooltip>
            )
          }
          return (
            <CalendarDayButton day={day} modifiers={modifiers} className={className} {...props} />
          )
        },
      }}
    />
  )
}

export default function Releases() {
  useDocumentTitle('Releases')

  const [releases, setReleases] = useState<GithubRelease[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [calOpen, setCalOpen] = useState(false)

  const fetchReleases = useCallback(async () => {
    const data = await getReleases()
    if (data === null) {
      setError(true)
    } else {
      setReleases(data)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchReleases().catch(() => undefined)
  }, [fetchReleases])

  const handleDateSelect = useCallback((id: number) => {
    setCalOpen(false)
    requestAnimationFrame(() => {
      document
        .querySelector(`[data-release-id="${id}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }, [])

  return (
    <PageMain>
      <PageHeader title="Releases" description="Niibot 的版本更新說明與功能紀錄。">
        {!loading && !error && releases.length > 0 && (
          <DropdownMenu open={calOpen} onOpenChange={setCalOpen}>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="flex size-9 items-center justify-center rounded-md border bg-background text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    aria-label="跳轉至發布日期"
                  >
                    <Icon icon="fa-solid fa-calendar-days" className="text-sub" />
                  </button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent>跳轉至發布日期</TooltipContent>
            </Tooltip>
            <DropdownMenuContent align="end" className="p-0">
              <ReleaseCalendar releases={releases} onSelect={handleDateSelect} />
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </PageHeader>

      {loading && (
        <div className="flex flex-col gap-section">
          {[0, 1, 2].map(i => (
            <ReleaseSkeleton key={i} />
          ))}
        </div>
      )}

      {!loading && error && (
        <Card>
          <CardContent className="flex flex-col items-center gap-element py-empty text-center">
            <Icon
              icon="fa-solid fa-circle-exclamation"
              size="md"
              wrapperClassName="text-status-warning"
            />
            <p className="text-sub text-muted-foreground">無法載入更新說明，請稍後再試。</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && releases.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-element py-empty text-center">
            <Icon icon="fa-solid fa-tag" size="md" wrapperClassName="text-muted-foreground" />
            <p className="text-sub text-muted-foreground">尚無任何版本發佈。</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && releases.length > 0 && (
        <Stagger inView className="flex flex-col gap-section">
          {releases.map(release => (
            <StaggerItem key={release.id} data-release-id={release.id}>
              <ReleaseCard release={release} />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </PageMain>
  )
}

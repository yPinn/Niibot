import { useCallback, useEffect, useRef, useState } from 'react'

import { getContainerLogs, getLogContainers, type LogContainer, type LogLine } from '@/api/admin'
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  Button,
  Icon,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'

const DEFAULT_CONTAINERS: LogContainer[] = [
  { name: 'niibot-api', label: 'API', running: false },
  { name: 'niibot-twitch', label: 'Twitch', running: false },
  { name: 'niibot-discord', label: 'Discord', running: false },
  { name: 'niibot-postgres', label: 'Postgres', running: false },
  { name: 'niibot-scrapling', label: 'Scrapling', running: false },
  { name: 'niibot-instafix', label: 'Instafix', running: false },
]

function parseDockerTs(raw: string): { ts: string; msg: string } {
  // Docker timestamp format: 2024-01-15T10:30:45.123456789Z <message>
  const m = raw.match(/^(\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2}))\.\S+Z?\s*(.*)$/)
  if (m) return { ts: m[2], msg: m[3] }
  return { ts: '', msg: raw }
}

function lineColor(msg: string, stream: string): string {
  if (/\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\b/i.test(msg)) return 'text-red-400'
  if (/\bwarn(ing)?\b/i.test(msg)) return 'text-amber-400'
  if (/\bdebug\b/i.test(msg)) return 'text-zinc-500'
  if (stream === 'stderr') return 'text-orange-300/80'
  return 'text-zinc-300'
}

function LogLineRow({ line, index }: { line: LogLine; index: number }) {
  const { ts, msg } = parseDockerTs(line.text)
  const color = lineColor(msg || line.text, line.stream)
  return (
    <div className="flex gap-2 min-w-0 hover:bg-white/[0.02] px-3 py-px group">
      <span className="text-zinc-700 shrink-0 select-none w-8 text-right tabular-nums group-hover:text-zinc-600">
        {index + 1}
      </span>
      {ts && <span className="text-zinc-600 shrink-0 tabular-nums">{ts}</span>}
      <span className={`${color} break-all whitespace-pre-wrap`}>{msg || line.text}</span>
    </div>
  )
}

export default function AdminLogs() {
  useDocumentTitle('Logs')

  const [containers, setContainers] = useState<LogContainer[]>(DEFAULT_CONTAINERS)
  const [selected, setSelected] = useState('niibot-api')
  const [tail, setTail] = useState(200)
  const [follow, setFollow] = useState(false)
  const [lines, setLines] = useState<LogLine[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const termRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getLogContainers()
      .then(cs => setContainers(cs))
      .catch(() => {})
  }, [])

  // Initial + container/tail-change fetch
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getContainerLogs(selected, tail)
      .then(data => {
        if (!cancelled) setLines(data.lines)
      })
      .catch(e => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selected, tail])

  // Silent poll for follow mode
  const pollFetch = useCallback(async () => {
    try {
      const data = await getContainerLogs(selected, tail)
      setLines(data.lines)
    } catch {
      // silent — don't disrupt the view on transient poll failure
    }
  }, [selected, tail])

  usePolling({ fetchFn: pollFetch, intervalMs: 5_000, enabled: follow })

  // Scroll to bottom when following
  useEffect(() => {
    if (follow && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight
    }
  }, [lines, follow])

  const currentContainer = containers.find(c => c.name === selected)

  const handleRefresh = () => {
    setLoading(true)
    setError(null)
    getContainerLogs(selected, tail)
      .then(data => setLines(data.lines))
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }

  return (
    <PageMain className="gap-0 p-0 lg:p-0 overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-page py-3 lg:px-page-lg border-b border-border/50 shrink-0">
        <div className="flex items-center gap-2">
          <Icon icon="fa-solid fa-file-lines" size="sm" wrapperClassName="text-muted-foreground" />
          <h1 className="text-card-title font-bold">Service Logs</h1>
          {currentContainer && (
            <Badge
              className={
                currentContainer.running
                  ? 'border-status-online/20 bg-status-online/10 text-status-online gap-1'
                  : 'border-status-offline/20 bg-status-offline/10 text-status-offline gap-1'
              }
            >
              <Icon
                icon={currentContainer.running ? 'fa-solid fa-circle' : 'fa-solid fa-circle-xmark'}
                size="xs"
              />
              {currentContainer.running ? 'running' : 'stopped'}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-label text-muted-foreground">Follow</span>
            <Switch checked={follow} onCheckedChange={setFollow} />
          </div>
          <Select value={String(tail)} onValueChange={v => setTail(Number(v))}>
            <SelectTrigger size="sm" className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="50">50 lines</SelectItem>
              <SelectItem value="100">100 lines</SelectItem>
              <SelectItem value="200">200 lines</SelectItem>
              <SelectItem value="500">500 lines</SelectItem>
              <SelectItem value="1000">1000 lines</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleRefresh}
            disabled={loading}
            aria-label="Refresh"
          >
            {loading ? (
              <Spinner />
            ) : (
              <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
            )}
          </Button>
        </div>
      </div>

      {/* Container tabs */}
      <div className="px-page lg:px-page-lg border-b border-border/50 overflow-x-auto shrink-0">
        <Tabs
          value={selected}
          onValueChange={v => {
            setSelected(v)
            setFollow(false)
          }}
        >
          <TabsList variant="line" className="h-10 bg-transparent gap-0">
            {containers.map(c => (
              <TabsTrigger key={c.name} value={c.name} className="gap-1.5 text-label px-3">
                <span
                  className={`size-1.5 rounded-full shrink-0 ${c.running ? 'bg-status-online' : 'bg-zinc-600'}`}
                />
                {c.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {/* Terminal */}
      <div
        ref={termRef}
        className="flex-1 min-h-0 overflow-auto bg-zinc-950 font-mono text-xs leading-5 py-2"
      >
        {loading && lines.length === 0 ? (
          <div className="flex items-center gap-2 px-4 py-3 text-zinc-500">
            <Spinner className="size-3" />
            <span>Loading logs…</span>
          </div>
        ) : error ? (
          <div className="px-4 py-3 text-red-400">{error}</div>
        ) : lines.length === 0 ? (
          <div className="px-4 py-3 text-zinc-600">No log output.</div>
        ) : (
          lines.map((line, i) => <LogLineRow key={i} line={line} index={i} />)
        )}
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-page lg:px-page-lg py-1.5 border-t border-zinc-800 bg-zinc-950 shrink-0">
        <span className="font-mono text-label text-zinc-600">
          {lines.length > 0 ? `${lines.length} lines · ${selected}` : selected}
        </span>
        {follow && (
          <span className="font-mono text-label text-status-online flex items-center gap-1.5">
            <Icon icon="fa-solid fa-circle" size="xs" />
            following
          </span>
        )}
      </div>
    </PageMain>
  )
}

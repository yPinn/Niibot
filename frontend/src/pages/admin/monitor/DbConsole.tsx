import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { type DbQueryResult, type DbTable, getDbSchema, runDbQuery } from '@/api/admin'
import { Icon, Spinner } from '@/components/primitives'
import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
} from '@/components/ui'
import { useInputInsert } from '@/hooks/useInputInsert'

const STARTER_SQL = 'SELECT channel_id, channel_name, enabled\nFROM channels\nLIMIT 50;'

/** The query a table click runs. Tables with columns the console role cannot
 *  read get an explicit column list so `SELECT *` doesn't error on the hidden
 *  ones; everything else stays `SELECT *`. */
function tablePeek(t: DbTable): string {
  const cols = t.has_hidden_columns ? t.columns.map(c => c.name).join(', ') : '*'
  return `SELECT ${cols}\nFROM ${t.name}\nLIMIT 50;`
}

/** Compact row estimate. `reltuples` is -1 (never analyzed) or 0 → unknown. */
function fmtRows(n: number | null): string | null {
  if (n == null || n <= 0) return null
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

export function DbConsole({
  reloadNonce,
  onLoadingChange,
}: {
  /** Bump to re-run the current query from the parent's shared refresh button. */
  reloadNonce?: number
  onLoadingChange?: (loading: boolean) => void
} = {}) {
  const [sql, setSql] = useState(STARTER_SQL)
  const [result, setResult] = useState<DbQueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [expandedCell, setExpandedCell] = useState<`${number}-${number}` | null>(null)
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  // ── Schema browser ──────────────────────────────────────────────────────────
  const [schema, setSchema] = useState<DbTable[] | null>(null)
  const [schemaError, setSchemaError] = useState<string | null>(null)
  const [tableFilter, setTableFilter] = useState('')
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())
  const [showSchema, setShowSchema] = useState(false) // mobile panel toggle
  const [showEmpty, setShowEmpty] = useState(false) // include empty relations

  const { inputRef, insertText } = useInputInsert<HTMLTextAreaElement>(sql, setSql)

  useEffect(() => {
    getDbSchema()
      .then(setSchema)
      .catch(e => setSchemaError(e instanceof Error ? e.message : String(e)))
  }, [])

  const hiddenEmptyCount = useMemo(
    () => (schema && !showEmpty ? schema.filter(t => t.is_empty).length : 0),
    [schema, showEmpty]
  )

  const filteredTables = useMemo(() => {
    if (!schema) return []
    const q = tableFilter.trim().toLowerCase()
    // A search term reveals empty relations too — otherwise they stay hidden.
    return schema.filter(t => {
      if (q) return t.name.toLowerCase().includes(q)
      return showEmpty || !t.is_empty
    })
  }, [schema, tableFilter, showEmpty])

  const toggleTable = useCallback((name: string) => {
    setExpandedTables(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }, [])

  // ── Query execution ─────────────────────────────────────────────────────────
  const sortedRows = useMemo(() => {
    if (!result || sortCol === null) return result?.rows ?? []
    return [...result.rows].sort((a, b) => {
      const av = a[sortCol],
        bv = b[sortCol]
      if (av === null && bv === null) return 0
      if (av === null) return 1
      if (bv === null) return -1
      const an = Number(av),
        bn = Number(bv)
      const cmp = !isNaN(an) && !isNaN(bn) ? an - bn : String(av).localeCompare(String(bv))
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [result, sortCol, sortDir])

  /** Columns whose every non-null value is a number → right-align + tabular-nums. */
  const numericCols = useMemo(() => {
    if (!result) return []
    return result.columns.map((_, j) => {
      let sawValue = false
      for (const r of result.rows) {
        const v = r[j]
        if (v === null) continue
        if (typeof v === 'boolean' || v === '' || isNaN(Number(v))) return false
        sawValue = true
      }
      return sawValue
    })
  }, [result])

  const handleSortClick = useCallback(
    (colIdx: number) => {
      setExpandedCell(null)
      if (sortCol === colIdx) {
        setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
      } else {
        setSortCol(colIdx)
        setSortDir('asc')
      }
    },
    [sortCol]
  )

  const runQuery = async (q: string) => {
    setLoading(true)
    setError(null)
    setResult(null)
    setExpandedCell(null)
    setSortCol(null)
    setSortDir('asc')
    try {
      setResult(await runDbQuery(q))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleRun = () => runQuery(sql)

  const runTable = (t: DbTable) => {
    const q = tablePeek(t)
    setSql(q)
    setShowSchema(false)
    runQuery(q)
  }

  // Parent's shared refresh button bumps `reloadNonce` — re-run whatever is in
  // the editor. Skip the initial render (nothing has been run yet).
  const didMount = useRef(false)
  useEffect(() => {
    if (!didMount.current) {
      didMount.current = true
      return
    }
    runQuery(sql)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadNonce])

  useEffect(() => {
    onLoadingChange?.(loading)
    return () => onLoadingChange?.(false)
  }, [loading, onLoadingChange])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      handleRun()
    }
  }

  const statusText = error
    ? error
    : result
      ? `${result.row_count} ${result.row_count === 1 ? 'row' : 'rows'}` +
        `${result.truncated ? '（已截斷至 500 列）' : ''} · ${result.duration_ms.toFixed(1)}ms`
      : 'SELECT only · 500 row cap · 5s timeout'

  const statusColor = error
    ? 'text-destructive'
    : result
      ? 'text-muted-foreground'
      : 'text-muted-foreground/50'

  // ── Schema panel (shared between mobile drawer and desktop sidebar) ──────────
  const schemaPanel = (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-border/30 px-2 pb-2 pt-2">
        <div className="relative">
          <Icon
            icon="fa-solid fa-magnifying-glass"
            size="xs"
            wrapperClassName="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground/40"
          />
          <input
            value={tableFilter}
            onChange={e => setTableFilter(e.target.value)}
            placeholder="搜尋資料表…"
            spellCheck={false}
            className="w-full rounded border border-border/40 bg-background py-1.5 pl-7 pr-2 font-mono text-sub outline-none focus:border-border"
          />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden py-1">
        {schemaError ? (
          <p className="px-3 py-2 text-sub text-destructive">{schemaError}</p>
        ) : !schema ? (
          <div className="flex items-center gap-2 px-3 py-2 text-muted-foreground">
            <Spinner className="size-3" />
            <span className="font-mono text-sub">載入結構…</span>
          </div>
        ) : filteredTables.length === 0 ? (
          <p className="px-3 py-2 text-sub text-muted-foreground/60">沒有符合的資料表</p>
        ) : (
          filteredTables.map(t => {
            const open = expandedTables.has(t.name)
            const rows = fmtRows(t.approx_rows)
            return (
              <div key={t.name} className="min-w-0">
                <div className="flex min-w-0 items-center">
                  <button
                    onClick={() => toggleTable(t.name)}
                    aria-label={open ? '收合欄位' : '展開欄位'}
                    className="flex w-9 shrink-0 items-center justify-center self-stretch text-muted-foreground/40 transition-colors hover:text-foreground"
                  >
                    <Icon icon={`fa-solid fa-chevron-${open ? 'down' : 'right'}`} size="xs" />
                  </button>
                  <button
                    onClick={() => runTable(t)}
                    title={tablePeek(t).replace(/\n/g, ' ')}
                    className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-2 text-left text-sub text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <span className="min-w-0 flex-1 truncate font-mono">{t.name}</span>
                    {t.kind === 'view' && (
                      <span className="shrink-0 rounded bg-muted px-1 text-label text-muted-foreground/50">
                        view
                      </span>
                    )}
                    {rows && (
                      <span className="shrink-0 tabular-nums text-label text-muted-foreground/30">
                        {rows}
                      </span>
                    )}
                  </button>
                </div>
                {open && (
                  <ul className="min-w-0 pb-1 pl-10 pr-2">
                    {t.columns.map(c => (
                      <li key={c.name} className="min-w-0">
                        <button
                          onClick={() => insertText(c.name)}
                          title={`插入「${c.name}」`}
                          className="flex w-full min-w-0 items-baseline gap-3 rounded px-1 py-1 text-left font-mono text-sub hover:bg-accent hover:text-accent-foreground"
                        >
                          <span className="min-w-0 flex-1 truncate text-foreground/70">
                            {c.name}
                          </span>
                          <span className="shrink-0 truncate text-label text-muted-foreground/40">
                            {c.type}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })
        )}
      </div>
      {schema && (hiddenEmptyCount > 0 || showEmpty) && (
        <button
          onClick={() => setShowEmpty(s => !s)}
          className="shrink-0 border-t border-border/30 px-3 py-1.5 text-left text-label text-muted-foreground/50 transition-colors hover:text-foreground"
        >
          {showEmpty ? '隱藏空資料表' : `顯示 ${hiddenEmptyCount} 張空資料表`}
        </button>
      )}
    </div>
  )

  return (
    <div className="flex flex-col md:flex-row flex-1 min-h-0 overflow-hidden bg-background">
      {/* ── Desktop schema sidebar ── */}
      <div className="hidden md:flex md:w-72 shrink-0 border-r border-border/40">{schemaPanel}</div>

      {/* ── Main area ── */}
      <div className="flex flex-col flex-1 min-h-0 min-w-0">
        {/* SQL input */}
        <div className="flex gap-3 p-3 border-b border-border/30 shrink-0">
          <Textarea
            ref={inputRef}
            value={sql}
            onChange={e => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={4}
            className="flex-1 font-mono text-sub leading-relaxed resize-y min-h-20 max-h-52"
            placeholder="SELECT ..."
            spellCheck={false}
          />
          <div className="flex flex-col gap-2 self-end shrink-0">
            <Button
              size="icon"
              variant="outline"
              className="md:hidden"
              onClick={() => setShowSchema(s => !s)}
              title="資料表結構"
            >
              <Icon icon="fa-solid fa-database" size="sm" />
            </Button>
            <Button
              size="icon"
              onClick={handleRun}
              disabled={loading || !sql.trim()}
              title="執行 (Ctrl+Enter)"
            >
              {loading ? (
                <Spinner className="size-4" />
              ) : (
                <Icon icon="fa-solid fa-play" size="sm" />
              )}
            </Button>
          </div>
        </div>

        {/* Mobile schema drawer */}
        {showSchema && (
          <div className="md:hidden shrink-0 max-h-64 border-b border-border/30">{schemaPanel}</div>
        )}

        {/* Results */}
        <div className="flex-1 min-h-0 min-w-0 overflow-auto">
          {error && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <Icon
                icon="fa-solid fa-triangle-exclamation"
                size="lg"
                wrapperClassName="text-destructive/70"
              />
              <span className="max-w-md font-mono text-sub text-destructive">{error}</span>
            </div>
          )}
          {!error && result && result.columns.length > 0 && (
            <Table className="w-auto">
              <TableHeader>
                <TableRow className="hover:bg-transparent border-border">
                  <TableHead className="sticky top-0 z-10 w-12 select-none bg-muted pr-3 text-right font-medium tabular-nums text-muted-foreground/50">
                    #
                  </TableHead>
                  {result.columns.map((col, j) => (
                    <TableHead
                      key={col}
                      className={`sticky top-0 z-10 cursor-pointer select-none whitespace-pre bg-muted font-medium text-muted-foreground transition-colors hover:text-foreground ${
                        numericCols[j] ? 'text-right' : ''
                      }`}
                      onClick={() => handleSortClick(j)}
                    >
                      <div
                        className={`flex items-center gap-1.5 ${numericCols[j] ? 'justify-end' : ''}`}
                      >
                        {col}
                        {sortCol === j && (
                          <Icon
                            icon={`fa-solid fa-arrow-${sortDir === 'asc' ? 'up' : 'down'}`}
                            size="xs"
                          />
                        )}
                      </div>
                    </TableHead>
                  ))}
                  {/* spacer so the header bg + zebra span the full width while
                      real columns stay content-sized */}
                  <TableHead className="sticky top-0 z-10 w-full bg-muted p-0" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedRows.map((row, i) => (
                  <TableRow
                    key={i}
                    className="border-border/40 font-mono text-sub odd:bg-muted/30 hover:bg-accent"
                  >
                    <TableCell className="select-none py-1.5 pr-3 text-right align-top tabular-nums text-muted-foreground/40">
                      {i + 1}
                    </TableCell>
                    {row.map((cell, j) => {
                      const key = `${i}-${j}` as const
                      const expanded = expandedCell === key
                      return (
                        <TableCell
                          key={j}
                          className={`py-1.5 align-top ${numericCols[j] ? 'text-right tabular-nums' : ''} ${cell !== null ? 'cursor-pointer' : ''}`}
                          onClick={() => cell !== null && setExpandedCell(expanded ? null : key)}
                        >
                          <div
                            className={
                              expanded
                                ? 'max-h-48 max-w-[72ch] overflow-y-auto whitespace-pre-wrap break-all text-foreground/90 transition-all duration-150'
                                : `max-h-6 max-w-[44ch] overflow-hidden truncate transition-all duration-150 ${cell === null ? 'italic text-muted-foreground/50' : 'text-foreground/80'}`
                            }
                            title={!expanded && cell !== null ? String(cell) : undefined}
                          >
                            {cell === null ? 'NULL' : String(cell)}
                          </div>
                        </TableCell>
                      )
                    })}
                    <TableCell className="p-0" />
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {!error && result && result.columns.length > 0 && result.row_count === 0 && (
            <div className="border-t border-border/40 px-3 py-2 font-mono text-sub text-muted-foreground/60">
              查詢沒有回傳任何列
            </div>
          )}
          {!error && result && result.columns.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
              <Icon icon="fa-solid fa-inbox" size="lg" />
              <span className="font-mono text-sub">此資料表目前沒有資料</span>
            </div>
          )}
          {!result && !error && !loading && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground/60">
              <Icon icon="fa-solid fa-terminal" size="lg" />
              <span className="font-mono text-sub">選一張資料表，或直接執行查詢。</span>
            </div>
          )}
        </div>

        {/* Status bar */}
        <div className="flex items-center px-3 py-1.5 border-t border-border/20 bg-background shrink-0">
          <span className={`font-mono text-sub truncate ${statusColor}`}>{statusText}</span>
        </div>
      </div>
    </div>
  )
}

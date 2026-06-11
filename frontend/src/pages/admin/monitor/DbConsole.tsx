import { useCallback, useMemo, useState } from 'react'

import { type DbQueryResult, runDbQuery } from '@/api/admin'
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

interface DbPreset {
  label: string
  sql: string
}

interface DbPresetGroup {
  group: string
  items: DbPreset[]
}

const DB_PRESETS: DbPresetGroup[] = [
  {
    group: 'Core',
    items: [
      {
        label: 'Channels',
        sql: 'SELECT channel_id, channel_name, display_name, enabled, created_at\nFROM channels\nORDER BY enabled DESC, channel_name\nLIMIT 100;',
      },
      {
        label: 'Tokens',
        sql: 'SELECT user_id, token_type, scopes, created_at, updated_at\nFROM tokens\nORDER BY updated_at DESC\nLIMIT 50;',
      },
      {
        label: 'Users',
        sql: 'SELECT id, display_name, avatar, created_at\nFROM users\nORDER BY created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Linked Accounts',
        sql: 'SELECT platform, platform_user_id, username, created_at\nFROM user_linked_accounts\nORDER BY created_at DESC\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Bot Config',
    items: [
      {
        label: 'Commands',
        sql: 'SELECT channel_id, command_name, command_type, enabled,\n       custom_response, min_role, usage_count\nFROM command_configs\nORDER BY channel_id, command_name\nLIMIT 200;',
      },
      {
        label: 'Cmd Aliases',
        sql: 'SELECT cc.channel_id, ca.alias, cc.command_name AS target_command, cc.command_type\nFROM command_aliases ca\nJOIN command_configs cc ON ca.command_id = cc.id\nORDER BY cc.channel_id, ca.alias\nLIMIT 100;',
      },
      {
        label: 'Cmd Stats',
        sql: 'SELECT channel_id, command_name, SUM(usage_count) AS total_uses\nFROM command_stats\nGROUP BY channel_id, command_name\nORDER BY total_uses DESC\nLIMIT 100;',
      },
      {
        label: 'Redemptions',
        sql: 'SELECT channel_id, action_type, reward_name, enabled\nFROM redemption_configs\nORDER BY channel_id\nLIMIT 100;',
      },
      {
        label: 'Event Configs',
        sql: 'SELECT channel_id, event_type, enabled\nFROM event_configs\nORDER BY channel_id, event_type\nLIMIT 100;',
      },
      {
        label: 'Timers',
        sql: 'SELECT channel_id, timer_name AS name, enabled, interval_seconds, message_template\nFROM timers\nORDER BY channel_id\nLIMIT 100;',
      },
      {
        label: 'Triggers',
        sql: 'SELECT channel_id, trigger_name AS name, enabled, pattern, response, usage_count\nFROM message_triggers\nORDER BY channel_id\nLIMIT 100;',
      },
    ],
  },
  {
    group: 'Analytics',
    items: [
      {
        label: 'Sessions',
        sql: 'SELECT * FROM v_session_summary\nORDER BY session_id DESC\nLIMIT 50;',
      },
      {
        label: 'Stream Events',
        sql: 'SELECT session_id, channel_id, event_type, username, display_name, occurred_at\nFROM stream_events\nORDER BY occurred_at DESC\nLIMIT 100;',
      },
      {
        label: 'Chatters',
        sql: 'SELECT channel_id, username, display_name, message_count, watch_seconds, last_message_at\nFROM chatter_stats\nORDER BY message_count DESC\nLIMIT 100;',
      },
      {
        label: 'Viewer Status',
        sql: 'SELECT channel_id, username, display_name,\n       is_subscribed, sub_tier, is_mod, is_vip, is_banned, follow_since\nFROM viewer_channel_status\nORDER BY channel_id\nLIMIT 100;',
      },
      {
        label: 'Attend. Streaks',
        sql: 'SELECT channel_id, user_id, streak_count, updated_at\nFROM viewer_attendance_streaks\nORDER BY streak_count DESC\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Features',
    items: [
      {
        label: 'Game Queue',
        sql: 'SELECT e.*,\n       s.enabled AS queue_open, s.group_size\nFROM game_queue_entries e\nLEFT JOIN game_queue_settings s ON e.channel_id = s.channel_id\nORDER BY e.channel_id, e.redeemed_at\nLIMIT 100;',
      },
      {
        label: 'Video Queue',
        sql: 'SELECT q.id, q.channel_id, q.video_type, q.video_id, q.title,\n       q.requested_by, q.status, q.created_at,\n       s.enabled AS queue_open, s.max_queue_size, s.max_duration_redemption\nFROM video_queue q\nLEFT JOIN video_queue_settings s ON q.channel_id = s.channel_id\nORDER BY q.created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Crosshairs',
        sql: 'SELECT id, channel_id, game, name, code, copy_count, created_at\nFROM crosshairs\nORDER BY copy_count DESC\nLIMIT 100;',
      },
    ],
  },
  {
    group: 'Activation',
    items: [
      {
        label: 'Codes',
        sql: 'SELECT platform_user_id, platform, expires_at, used_at\nFROM activation_codes\nORDER BY expires_at DESC\nLIMIT 50;',
      },
      {
        label: 'Requests',
        sql: 'SELECT ar.id, ar.platform, ar.platform_user_id, u.display_name,\n       ar.status, ar.note, ar.created_at\nFROM activation_requests ar\nLEFT JOIN users u ON ar.user_id = u.id\nORDER BY ar.created_at DESC\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Payments',
    items: [
      {
        label: 'Donations',
        sql: 'SELECT id, channel_id, amount, platform, status, message, created_at\nFROM donation_orders\nORDER BY created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Pay Configs',
        sql: 'SELECT * FROM user_payment_configs\nLIMIT 50;',
      },
    ],
  },
  {
    group: 'Discord',
    items: [
      {
        label: 'Discord Users',
        sql: 'SELECT user_id, username, display_name, created_at\nFROM discord_users\nORDER BY created_at DESC\nLIMIT 50;',
      },
      {
        label: 'Birthdays',
        sql: 'SELECT user_id, month, day, year\nFROM discord_birthdays\nORDER BY month, day\nLIMIT 100;',
      },
      {
        label: 'BD Settings',
        sql: 'SELECT * FROM discord_birthday_settings\nLIMIT 50;',
      },
    ],
  },
]

export function DbConsole() {
  const [sql, setSql] = useState(DB_PRESETS[0].items[0].sql)
  const [activePreset, setActivePreset] = useState<string>('Channels')
  const [result, setResult] = useState<DbQueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [expandedCell, setExpandedCell] = useState<`${number}-${number}` | null>(null)
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

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

  const handlePreset = (preset: DbPreset) => {
    setSql(preset.sql)
    setActivePreset(preset.label)
    runQuery(preset.sql)
  }

  const handleRun = () => runQuery(sql)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      handleRun()
    }
  }

  const statusText = error
    ? error
    : result
      ? `${result.row_count} ${result.row_count === 1 ? 'row' : 'rows'} · ${result.duration_ms.toFixed(1)}ms`
      : 'SELECT only · 500 row cap · 5s timeout'

  const statusColor = error
    ? 'text-destructive'
    : result
      ? 'text-muted-foreground'
      : 'text-muted-foreground/50'

  return (
    <div className="flex flex-col md:flex-row flex-1 min-h-0 overflow-hidden bg-background">
      {/* ── Preset sidebar / mobile strip ── */}
      <div className="flex flex-row overflow-x-auto shrink-0 border-b border-border/30 md:flex-col md:w-44 md:border-b-0 md:border-r md:overflow-x-hidden md:overflow-y-auto md:py-1">
        {DB_PRESETS.map(group => (
          <div key={group.group} className="flex flex-row md:flex-col">
            <div className="hidden md:block px-3 pt-3 pb-1 text-muted-foreground/60 font-medium uppercase tracking-wide text-label select-none">
              {group.group}
            </div>
            {group.items.map(item => (
              <button
                key={item.label}
                onClick={() => handlePreset(item)}
                className={`whitespace-nowrap md:w-full text-left px-3 py-2 md:py-1 text-label truncate transition-colors ${
                  activePreset === item.label
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* ── Main area ── */}
      <div className="flex flex-col flex-1 min-h-0 min-w-0">
        {/* SQL input */}
        <div className="flex gap-2 p-3 border-b border-border/30 shrink-0">
          <Textarea
            value={sql}
            onChange={e => {
              setSql(e.target.value)
              setActivePreset('')
            }}
            onKeyDown={handleKeyDown}
            rows={4}
            className="flex-1 font-mono text-label text-foreground bg-muted border-border resize-y min-h-18 max-h-48 focus-visible:ring-1 focus-visible:ring-ring"
            placeholder="SELECT ..."
            spellCheck={false}
          />
          <Button
            size="sm"
            onClick={handleRun}
            disabled={loading || !sql.trim()}
            className="self-end shrink-0"
            title="Run (Ctrl+Enter)"
          >
            {loading ? <Spinner className="size-3" /> : <Icon icon="fa-solid fa-play" size="xs" />}
          </Button>
        </div>

        {/* Results */}
        <div className="flex-1 min-h-0 overflow-auto">
          {result && result.row_count > 0 && (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-border">
                  <TableHead className="sticky top-0 bg-muted text-muted-foreground/50 font-medium w-10 text-right tabular-nums select-none">
                    #
                  </TableHead>
                  {result.columns.map((col, j) => (
                    <TableHead
                      key={col}
                      className="sticky top-0 bg-muted text-muted-foreground whitespace-pre font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => handleSortClick(j)}
                    >
                      <div className="flex items-center gap-1.5">
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
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedRows.map((row, i) => (
                  <TableRow
                    key={i}
                    className="hover:bg-accent border-border/50 font-mono text-label"
                  >
                    <TableCell className="text-muted-foreground/40 text-right py-1 tabular-nums select-none">
                      {i + 1}
                    </TableCell>
                    {row.map((cell, j) => {
                      const key = `${i}-${j}` as const
                      const expanded = expandedCell === key
                      return (
                        <TableCell
                          key={j}
                          className={`py-1 ${cell !== null ? 'cursor-pointer' : ''}`}
                          onClick={() => cell !== null && setExpandedCell(expanded ? null : key)}
                        >
                          <div
                            className={
                              expanded
                                ? 'max-h-48 overflow-y-auto whitespace-pre-wrap break-all text-foreground/90 max-w-[60ch] transition-all duration-150'
                                : `max-h-6 overflow-hidden truncate max-w-[36ch] transition-all duration-150 ${cell === null ? 'text-muted-foreground/50 italic' : 'text-foreground/80'}`
                            }
                            title={!expanded && cell !== null ? String(cell) : undefined}
                          >
                            {cell === null ? 'NULL' : String(cell)}
                          </div>
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {result && result.row_count === 0 && !error && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
              <Icon icon="fa-solid fa-inbox" size="lg" />
              <span className="font-mono text-label">No rows returned.</span>
            </div>
          )}
          {!result && !error && !loading && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground/60">
              <Icon icon="fa-solid fa-terminal" size="lg" />
              <span className="font-mono text-label">Select a preset or run a query.</span>
            </div>
          )}
        </div>

        {/* Status bar */}
        <div className="flex items-center px-3 py-1.5 border-t border-border/20 bg-background shrink-0">
          <span className={`font-mono text-label truncate ${statusColor}`}>{statusText}</span>
        </div>
      </div>
    </div>
  )
}

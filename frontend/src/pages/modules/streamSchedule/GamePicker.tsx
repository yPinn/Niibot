import { useEffect, useId, useRef, useState } from 'react'

import {
  searchStreamScheduleGames,
  type StreamScheduleGameSearchResult,
} from '@/api/streamSchedule'
import { Icon, Spinner } from '@/components/primitives'
import { Button, Input, Label } from '@/components/ui'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { cn } from '@/lib/utils'

export interface GameValue {
  id: string
  name: string
}

interface GamePickerProps {
  id?: string
  label?: string
  labelClassName?: string
  inputClassName?: string
  value: GameValue | null
  onChange: (value: GameValue | null) => void
  onPendingSelectionChange?: (pending: boolean) => void
}

/** Twitch box art URLs are a template ("…-{width}x{height}.jpg") the caller
 * fills in, not a ready image URL — same convention across every Helix
 * endpoint that returns box art. */
function thumbnailUrl(template: string | null, width: number, height: number): string | null {
  if (!template) return null
  return template.replace('{width}', String(width)).replace('{height}', String(height))
}

/** Fuzzy category search-as-you-type, backed by the same Twitch endpoint
 * Twitch's own category picker uses — unlike a plain text field, this
 * guarantees whatever gets saved is a real, exact category. Shows box art so
 * the streamer can visually confirm they didn't pick a similarly-named
 * category by mistake (e.g. "Just Chatting" vs. a copycat fan-made one). */
export function GamePicker({
  id,
  label = '遊戲分類（選填）',
  labelClassName,
  inputClassName,
  value,
  onChange,
  onPendingSelectionChange,
}: GamePickerProps) {
  const generatedId = useId()
  const inputId = id ?? `game-picker-${generatedId}`
  const listboxId = `${inputId}-listbox`
  const hintId = `${inputId}-hint`
  const [query, setQuery] = useState(value?.name ?? '')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<StreamScheduleGameSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [searchState, setSearchState] = useState<'idle' | 'success' | 'error'>('idle')
  const [activeIndex, setActiveIndex] = useState(-1)
  // Cosmetic only — never part of the value the parent stores/saves. Known
  // immediately when picked fresh from the dropdown; for a value the parent
  // mounted us with (e.g. editing an already-saved segment) it starts blank
  // and gets backfilled once below, since the API only persists id/name.
  const [boxArt, setBoxArt] = useState<string | null>(null)
  const debouncedQuery = useDebouncedValue(query, 300)
  const blurTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    // Selected value already matches the query text — nothing to search for.
    if (!open || !debouncedQuery.trim() || debouncedQuery === value?.name) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResults([])
      setSearchState('idle')
      return
    }
    let cancelled = false
    setLoading(true)
    searchStreamScheduleGames(debouncedQuery)
      .then(matches => {
        if (!cancelled) {
          setResults(matches)
          setSearchState('success')
          setActiveIndex(-1)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResults([])
          setSearchState('error')
          setActiveIndex(-1)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, open])

  useEffect(() => {
    // One-shot backfill for a value we were mounted with but have no art for
    // yet (see `boxArt` comment above). Runs once per mount, matching the
    // "remount on identity change" pattern the sheets around this component
    // already use instead of re-syncing on every prop change.
    if (!value) return
    let cancelled = false
    searchStreamScheduleGames(value.name)
      .then(matches => {
        if (cancelled) return
        const match = matches.find(m => m.id === value.id)
        if (match) setBoxArt(match.box_art_url)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(
    () => () => {
      if (blurTimeout.current) clearTimeout(blurTimeout.current)
    },
    []
  )

  const select = (game: StreamScheduleGameSearchResult) => {
    onChange({ id: game.id, name: game.name })
    onPendingSelectionChange?.(false)
    setQuery(game.name)
    setBoxArt(game.box_art_url)
    setOpen(false)
  }

  const clear = () => {
    onChange(null)
    onPendingSelectionChange?.(false)
    setQuery('')
    setBoxArt(null)
    setOpen(false)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      if (results.length === 0) return
      setActiveIndex(current => {
        if (event.key === 'ArrowDown') return Math.min(current + 1, results.length - 1)
        return current <= 0 ? results.length - 1 : current - 1
      })
      return
    }
    if (event.key === 'Enter' && open && activeIndex >= 0) {
      event.preventDefault()
      const activeResult = results[activeIndex]
      if (activeResult) select(activeResult)
    }
  }

  const hasPendingSelection = query.trim().length > 0 && value === null
  const showSearchPanel =
    open &&
    query.trim().length > 0 &&
    (loading || results.length > 0 || searchState === 'success' || searchState === 'error')

  return (
    <div className="flex flex-col gap-2">
      {label && (
        <Label htmlFor={inputId} className={labelClassName}>
          {label}
        </Label>
      )}
      <div className="relative">
        <div className="relative">
          <Input
            id={inputId}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={showSearchPanel}
            aria-controls={showSearchPanel ? listboxId : undefined}
            aria-activedescendant={
              open && activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined
            }
            aria-describedby={hasPendingSelection ? hintId : undefined}
            aria-invalid={hasPendingSelection && !open}
            value={query}
            onChange={e => {
              const nextQuery = e.target.value
              if (value) onChange(null)
              onPendingSelectionChange?.(nextQuery.trim().length > 0)
              setQuery(nextQuery)
              setResults([])
              setSearchState('idle')
              setActiveIndex(-1)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              // Delay so a click on a dropdown item registers before the list unmounts.
              blurTimeout.current = setTimeout(() => setOpen(false), 150)
            }}
            placeholder="搜尋 Twitch 遊戲分類…"
            className={cn(value ? 'pl-9' : undefined, 'pr-8', inputClassName)}
            autoComplete="off"
          />
          {value && (
            <img
              src={thumbnailUrl(boxArt, 24, 32) ?? undefined}
              alt=""
              className={cn(
                'absolute left-1.5 top-1/2 h-6 w-4.5 -translate-y-1/2 rounded-sm object-cover',
                !boxArt && 'invisible'
              )}
            />
          )}
          {value && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={cn('absolute right-0 top-0 size-9', inputClassName && 'size-8')}
              onClick={clear}
              aria-label="清除遊戲分類"
            >
              <Icon icon="fa-solid fa-xmark" wrapperClassName="size-3" />
            </Button>
          )}
        </div>

        {showSearchPanel && (
          <div
            id={results.length === 0 ? listboxId : undefined}
            className="absolute z-raised mt-1 w-full rounded-md border border-border bg-popover text-popover-foreground shadow-md"
          >
            {loading ? (
              <div className="flex items-center gap-2 px-3 py-2 text-sub text-muted-foreground">
                <Spinner className="size-3.5" />
                搜尋中…
              </div>
            ) : results.length > 0 ? (
              <ul id={listboxId} role="listbox" className="max-h-72 overflow-y-auto py-1">
                {results.map((game, index) => (
                  <li
                    id={`${listboxId}-option-${index}`}
                    key={game.id}
                    role="option"
                    aria-selected={activeIndex === index}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-sub hover:bg-accent',
                      activeIndex === index && 'bg-accent'
                    )}
                    onMouseDown={event => event.preventDefault()}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => select(game)}
                  >
                    <img
                      src={thumbnailUrl(game.box_art_url, 32, 43) ?? undefined}
                      alt=""
                      className={cn(
                        'h-10.75 w-8 shrink-0 rounded-sm object-cover',
                        !game.box_art_url && 'invisible'
                      )}
                    />
                    {game.name}
                  </li>
                ))}
              </ul>
            ) : (
              <div role="status" className="px-3 py-2 text-sub text-muted-foreground">
                {searchState === 'error'
                  ? '無法搜尋 Twitch 分類，請稍後再試'
                  : '找不到符合的 Twitch 分類'}
              </div>
            )}
          </div>
        )}
      </div>
      {hasPendingSelection && (
        <p id={hintId} className="text-label text-destructive">
          請從搜尋結果選擇分類
        </p>
      )}
    </div>
  )
}

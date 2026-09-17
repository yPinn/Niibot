import { memo, useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  applyImport,
  getImportPreview,
  getImportSources,
  getNightbotOauthUrl,
  type ImportItem,
  type ImportPreview,
  type ImportSection,
  type ImportSourceInfo,
  type ImportSourceName,
  previewStreamElements,
} from '@/api/commandImport'
import { Icon, OptionPicker, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Switch,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

import { ROLE_LABELS } from './constants'

/** How the imported commands should start out. */
type StartMode = 'source' | 'off' | 'on'

const SOURCE_LABELS: Record<ImportSourceName, string> = {
  nightbot: 'Nightbot',
  streamelements: 'StreamElements',
}

const SECTION_ORDER: ImportSection[] = ['builtin', 'custom', 'trigger', 'unsupported']

const SECTION_TITLES: Record<ImportSection, string> = {
  builtin: '對應到內建指令',
  custom: '新增為自訂指令',
  trigger: '關鍵字自動回應',
  unsupported: '無法匯入',
}

const SECTION_HINTS: Record<ImportSection, string> = {
  builtin: '這些指令 Niibot 本來就有，改成直接啟用內建版本',
  custom: '會在「自訂」分頁建立新的指令',
  trigger: '會在「自訂」分頁建立關鍵字觸發的自動回應',
  unsupported: '列出來讓你知道少了什麼，不會寫入任何東西',
}

const STATUS_BADGE: Record<ImportItem['status'], { label: string; className: string } | null> = {
  ok: null,
  review: { label: '需確認', className: 'bg-warning/15 text-warning border-warning/30' },
  conflict: { label: '已存在', className: 'bg-muted text-muted-foreground' },
  unsupported: { label: '不支援', className: 'bg-destructive/10 text-destructive' },
}

export interface ImportSheetProps {
  open: boolean
  /** Set when returning from the Nightbot OAuth redirect. */
  initialImportId?: string | null
  onImported: () => void
  onClose: () => void
}

export function ImportSheet({ open, initialImportId, onImported, onClose }: ImportSheetProps) {
  const [sources, setSources] = useState<ImportSourceInfo[] | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  // Presence = the row is ticked, value = it should start enabled. One store,
  // so a row can never be unticked and still carry a stale enabled flag.
  const [selection, setSelection] = useState<Map<string, boolean>>(new Map())
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)

  const reset = useCallback(() => {
    setPreview(null)
    setSelection(new Map())
  }, [])

  const adopt = useCallback((data: ImportPreview) => {
    setPreview(data)
    setSelection(new Map(Object.entries(data.default_selection)))
  }, [])

  useEffect(() => {
    if (!open) return
    getImportSources()
      .then(setSources)
      .catch(() => setSources([]))
  }, [open])

  useEffect(() => {
    if (!open || !initialImportId) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    getImportPreview(initialImportId)
      .then(adopt)
      .catch(e => toastApiError(e, '讀取匯入清單失敗'))
      .finally(() => setLoading(false))
  }, [open, initialImportId, adopt])

  const loadStreamElements = async () => {
    setLoading(true)
    try {
      adopt(await previewStreamElements())
    } catch (e) {
      toastApiError(e, '讀取 StreamElements 指令失敗')
    } finally {
      setLoading(false)
    }
  }

  const startNightbot = async () => {
    setLoading(true)
    try {
      const { oauth_url } = await getNightbotOauthUrl()
      window.location.href = oauth_url
    } catch (e) {
      toastApiError(e, '無法開始 Nightbot 授權')
      setLoading(false)
    }
  }

  const applyStartMode = (mode: StartMode) => {
    if (!preview) return
    const wasEnabled = new Map(preview.items.map(i => [i.key, i.source_enabled]))
    setSelection(prev => {
      const next = new Map(prev)
      for (const key of next.keys()) {
        next.set(key, mode === 'on' ? true : mode === 'off' ? false : !!wasEnabled.get(key))
      }
      return next
    })
  }

  const togglePicked = useCallback((key: string) => {
    setSelection(prev => {
      const next = new Map(prev)
      if (next.has(key)) next.delete(key)
      else next.set(key, false)
      return next
    })
  }, [])

  const setEnabled = useCallback((key: string, enabled: boolean) => {
    setSelection(prev => new Map(prev).set(key, enabled))
  }, [])

  const grouped = useMemo(() => {
    const items = preview?.items ?? []
    return Object.fromEntries(
      SECTION_ORDER.map(s => [s, items.filter(i => i.section === s)])
    ) as Record<ImportSection, ImportItem[]>
  }, [preview])

  // Derived, so flipping one row's switch cannot leave a stale mode highlighted.
  const startMode = useMemo((): StartMode | null => {
    const values = [...selection.values()]
    if (values.length === 0) return null
    if (values.every(v => v)) return 'on'
    if (values.every(v => !v)) return 'off'
    return null
  }, [selection])

  const handleApply = async () => {
    if (!preview) return
    if (selection.size === 0) {
      toast.error('請至少勾選一個項目')
      return
    }
    setApplying(true)
    try {
      const result = await applyImport(preview.import_id, Object.fromEntries(selection))
      const parts = [`匯入 ${result.created} 筆`]
      if (result.enabled) parts.push(`啟用 ${result.enabled} 筆`)
      if (result.skipped) parts.push(`跳過 ${result.skipped} 筆`)
      if (result.failed) parts.push(`失敗 ${result.failed} 筆`)
      toast.success(parts.join('，'))
      if (result.errors.length) toast.error(result.errors[0])
      onImported()
      reset()
      onClose()
    } catch (e) {
      toastApiError(e, '匯入失敗')
    } finally {
      setApplying(false)
    }
  }

  const handleOpenChange = (next: boolean) => {
    if (next) return
    reset()
    onClose()
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent className="flex flex-col sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>匯入指令</SheetTitle>
          <SheetDescription>
            {preview
              ? `來源 ${SOURCE_LABELS[preview.source]} · ${preview.source_channel}`
              : '從你現在使用的機器人把自訂指令搬過來'}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-4 pb-4">
          {loading ? (
            <div className="flex items-center justify-center py-empty">
              <Spinner />
            </div>
          ) : preview ? (
            <PreviewList
              grouped={grouped}
              selection={selection}
              startMode={startMode}
              onStartMode={applyStartMode}
              onTogglePicked={togglePicked}
              onSetEnabled={setEnabled}
            />
          ) : (
            <SourcePicker
              sources={sources}
              onStreamElements={loadStreamElements}
              onNightbot={startNightbot}
            />
          )}
        </div>

        {preview && (
          <SheetFooter>
            <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={applying}>
              取消
            </Button>
            <Button onClick={handleApply} disabled={applying || selection.size === 0}>
              {applying ? <Spinner className="mr-2 size-3" /> : null}
              匯入勾選的 {selection.size} 筆
            </Button>
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  )
}

// ---------------------------------------------------------------------------

function SourcePicker({
  sources,
  onStreamElements,
  onNightbot,
}: {
  sources: ImportSourceInfo[] | null
  onStreamElements: () => void
  onNightbot: () => void
}) {
  if (sources === null) {
    return (
      <div className="flex items-center justify-center py-empty">
        <Spinner />
      </div>
    )
  }

  const nightbot = sources.find(s => s.source === 'nightbot')

  return (
    <div className="space-y-3 pt-2">
      <button
        type="button"
        onClick={onStreamElements}
        className="w-full rounded-lg border border-border p-4 text-left transition-colors hover:border-primary/60 hover:bg-accent/40"
      >
        <div className="font-semibold">StreamElements</div>
        <p className="text-label text-muted-foreground">直接讀取，不需要額外授權</p>
      </button>

      <button
        type="button"
        onClick={onNightbot}
        disabled={!nightbot?.available}
        className="w-full rounded-lg border border-border p-4 text-left transition-colors hover:border-primary/60 hover:bg-accent/40 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:border-border disabled:hover:bg-transparent"
      >
        <div className="font-semibold">Nightbot</div>
        <p className="text-label text-muted-foreground">
          {nightbot?.available
            ? '需要授權 Niibot 讀取你的指令，否則抓到的內容會缺少變數'
            : (nightbot?.reason ?? '目前無法使用')}
        </p>
      </button>
    </div>
  )
}

function PreviewList({
  grouped,
  selection,
  startMode,
  onStartMode,
  onTogglePicked,
  onSetEnabled,
}: {
  grouped: Record<ImportSection, ImportItem[]>
  selection: Map<string, boolean>
  startMode: StartMode | null
  onStartMode: (mode: StartMode) => void
  onTogglePicked: (key: string) => void
  onSetEnabled: (key: string, enabled: boolean) => void
}) {
  return (
    <div className="space-y-5 pt-2">
      <OptionPicker<StartMode>
        label="匯入後狀態"
        value={startMode ?? ('' as StartMode)}
        onChange={onStartMode}
        options={[
          { value: 'off', label: '全部停用' },
          { value: 'source', label: '沿用原本' },
          { value: 'on', label: '全部啟用' },
        ]}
      />

      {SECTION_ORDER.map(section => {
        const items = grouped[section]
        if (items.length === 0) return null
        return (
          <section key={section} className="space-y-2">
            <div>
              <h3 className="text-label font-semibold">
                {SECTION_TITLES[section]}
                <span className="ml-1.5 text-muted-foreground">({items.length})</span>
              </h3>
              <p className="text-label text-muted-foreground">{SECTION_HINTS[section]}</p>
            </div>
            <ul className="divide-y divide-border/60 rounded-lg border border-border">
              {items.map(item => (
                <ImportRow
                  key={item.key}
                  item={item}
                  picked={selection.has(item.key)}
                  enabled={selection.get(item.key) ?? false}
                  onTogglePicked={onTogglePicked}
                  onSetEnabled={onSetEnabled}
                />
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

/** Memoized: an import can run to 150+ rows and every toggle re-renders the list. */
const ImportRow = memo(function ImportRow({
  item,
  picked,
  enabled,
  onTogglePicked,
  onSetEnabled,
}: {
  item: ImportItem
  picked: boolean
  enabled: boolean
  onTogglePicked: (key: string) => void
  onSetEnabled: (key: string, enabled: boolean) => void
}) {
  const selectable = item.section !== 'unsupported'
  const badge = STATUS_BADGE[item.status]
  const rewritten = item.original_response && item.original_response !== item.response

  return (
    <li className="flex items-start gap-3 p-3">
      <button
        type="button"
        role="checkbox"
        aria-checked={picked}
        aria-label={`選取 ${item.source_name}`}
        disabled={!selectable}
        onClick={() => onTogglePicked(item.key)}
        className="mt-0.5 shrink-0 text-muted-foreground disabled:opacity-40"
      >
        <Icon
          icon={picked ? 'fa-solid fa-square-check' : 'fa-regular fa-square'}
          wrapperClassName={picked ? 'size-4 text-primary' : 'size-4'}
        />
      </button>

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-sub">{item.source_name}</span>
          {badge && (
            <Badge variant="outline" className={`px-1.5 text-label ${badge.className}`}>
              {badge.label}
            </Badge>
          )}
          {item.min_role !== 'everyone' && (
            <Badge variant="secondary" className="px-1.5 text-label">
              {ROLE_LABELS[item.min_role] ?? item.min_role}
            </Badge>
          )}
        </div>

        {item.response && (
          <p className="truncate font-mono text-label text-muted-foreground">{item.response}</p>
        )}
        {rewritten && (
          <p className="truncate font-mono text-label text-muted-foreground/70 line-through">
            {item.original_response}
          </p>
        )}
        {item.notes.map(note => (
          <p key={note} className="text-label text-muted-foreground">
            · {note}
          </p>
        ))}
      </div>

      {selectable && (
        <Switch
          aria-label={`匯入後啟用 ${item.source_name}`}
          checked={enabled}
          disabled={!picked}
          onCheckedChange={value => onSetEnabled(item.key, value)}
        />
      )}
    </li>
  )
})

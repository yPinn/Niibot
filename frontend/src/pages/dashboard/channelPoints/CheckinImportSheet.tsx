import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  applyCheckinImport,
  type CheckinIdentityMapping,
  type CheckinImportApplyResult,
  type CheckinImportCanonicalField,
  type CheckinImportColumnMapping,
  type CheckinImportColumns,
  type CheckinImportPreview,
  type CheckinImportRow,
  type CheckinImportRowStatus,
  inspectCheckinImportColumns,
  previewCheckinImport,
  remapCheckinImportIdentities,
} from '@/api/checkin'
import { Icon, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Input,
  Label,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

interface CheckinImportSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultTimezone: string
}

type InputMode = 'upload' | 'google'

const STATUS_LABELS = {
  ready: '可匯入',
  review: '待確認',
  invalid: '格式錯誤',
  unresolved: '待配對',
  conflict: '資料衝突',
} satisfies Record<CheckinImportRowStatus, string>

const STATUS_PRIORITY: Record<CheckinImportRowStatus, number> = {
  unresolved: 0,
  review: 1,
  conflict: 2,
  invalid: 2,
  ready: 3,
}

type MappingField = {
  field: CheckinImportCanonicalField
  label: string
  hint: string
}

const REQUIRED_MAPPING_FIELDS: ReadonlyArray<MappingField> = [
  { field: 'username', label: 'Twitch 帳號', hint: '如 Username' },
  { field: 'total_days', label: '累積天數', hint: '如 Count，必填' },
  { field: 'last_checkin_date', label: '最後簽到', hint: '如 LastDate，必填' },
]

const OPTIONAL_MAPPING_FIELDS: ReadonlyArray<MappingField> = [
  { field: 'display_name', label: '顯示名稱', hint: '如 DisplayName，可作觀眾識別' },
  { field: 'platform_user_id', label: 'Twitch ID', hint: '可作觀眾識別' },
  { field: 'current_streak', label: '連續天數', hint: '如 Streak' },
  { field: 'daily_order', label: '最後簽到日順位', hint: '如 TodayOrder' },
]

const today = () => new Date().toISOString().slice(0, 10)

function hasRequiredMapping(mapping: CheckinImportColumnMapping) {
  return (
    (mapping.username !== undefined ||
      mapping.display_name !== undefined ||
      mapping.platform_user_id !== undefined) &&
    mapping.total_days !== undefined &&
    mapping.last_checkin_date !== undefined
  )
}

function rowName(row: CheckinImportRow) {
  return (
    row.display_name ??
    row.username ??
    row.source_display_name ??
    (row.source_username ? `@${row.source_username}` : `第 ${row.source_row} 列`)
  )
}

function sourceIdentity(row: CheckinImportRow) {
  if (row.source_username) return `@${row.source_username}`
  if (row.source_display_name) return row.source_display_name
  if (row.source_user_id) return '來源 Twitch ID'
  return `第 ${row.source_row} 列`
}

function showUsername(row: CheckinImportRow) {
  if (!row.username || !row.display_name) return false
  return row.username.localeCompare(row.display_name, undefined, { sensitivity: 'accent' }) !== 0
}

function downloadExample(delimiter: ',' | '\t', extension: 'csv' | 'tsv') {
  const rows = [
    ['Username', 'Count', 'LastDate', 'Streak', 'TodayOrder'],
    ['viewer_name', '15', '2026-09-10', '3', '5'],
  ]
  const blob = new Blob([rows.map(row => row.join(delimiter)).join('\r\n') + '\r\n'], {
    type:
      extension === 'csv' ? 'text/csv;charset=utf-8' : 'text/tab-separated-values;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `checkin-import-example.${extension}`
  anchor.click()
  URL.revokeObjectURL(url)
}

function ColumnMappingFields({
  fields,
  headers,
  mapping,
  onChange,
}: {
  fields: ReadonlyArray<MappingField>
  headers: ReadonlyArray<string>
  mapping: CheckinImportColumnMapping
  onChange: (field: CheckinImportCanonicalField, rawIndex: string) => void
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {fields.map(({ field, label, hint }) => (
        <div key={field} className="space-y-1.5">
          <Label htmlFor={`checkin-map-${field}`}>
            {label} <span className="text-muted-foreground">（{hint}）</span>
          </Label>
          <select
            id={`checkin-map-${field}`}
            aria-label={`${label} 對應欄位`}
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={mapping[field]?.toString() ?? ''}
            onChange={event => onChange(field, event.target.value)}
          >
            <option value="">不匯入</option>
            {headers.map((header, index) => (
              <option
                key={`${index}-${header}`}
                value={index}
                disabled={
                  !header ||
                  Object.entries(mapping).some(
                    ([mappedField, mappedIndex]) => mappedField !== field && mappedIndex === index
                  )
                }
              >
                {index + 1}. {header || '（空白欄位）'}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  )
}

export function CheckinImportSheet({
  open,
  onOpenChange,
  defaultTimezone,
}: CheckinImportSheetProps) {
  const [mode, setMode] = useState<InputMode>('upload')
  const [source, setSource] = useState('chiwabots')
  const [sourceTimezone, setSourceTimezone] = useState(defaultTimezone || 'Asia/Taipei')
  const [throughDate, setThroughDate] = useState(today)
  const [upload, setUpload] = useState<File | null>(null)
  const [sheetUrl, setSheetUrl] = useState('')
  const [columns, setColumns] = useState<CheckinImportColumns | null>(null)
  const [columnMapping, setColumnMapping] = useState<CheckinImportColumnMapping>({})
  const [mappingOpen, setMappingOpen] = useState(false)
  const [preview, setPreview] = useState<CheckinImportPreview | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [oldSourceDisabled, setOldSourceDisabled] = useState(false)
  const [loading, setLoading] = useState(false)
  const [inspecting, setInspecting] = useState(false)
  const [applying, setApplying] = useState(false)
  const [receipt, setReceipt] = useState<CheckinImportApplyResult | null>(null)
  const [mappingRowKey, setMappingRowKey] = useState<string | null>(null)
  const [identityTargetType, setIdentityTargetType] =
    useState<CheckinIdentityMapping['targetType']>('username')
  const [identityTarget, setIdentityTarget] = useState('')
  const [remapping, setRemapping] = useState(false)
  const [showReceiptDetails, setShowReceiptDetails] = useState(false)

  const selected = useMemo(() => new Set(selectedKeys), [selectedKeys])
  const counts = useMemo(() => {
    const result = { ready: 0, review: 0, invalid: 0, unresolved: 0, conflict: 0 }
    for (const row of preview?.rows ?? []) result[row.status] += 1
    return result
  }, [preview])
  const sortedRows = useMemo(
    () =>
      [...(preview?.rows ?? [])].sort(
        (left, right) =>
          STATUS_PRIORITY[left.status] - STATUS_PRIORITY[right.status] ||
          left.source_row - right.source_row
      ),
    [preview]
  )

  const hasSource = mode === 'upload' ? Boolean(upload) : Boolean(sheetUrl.trim())
  const mappingReady = hasRequiredMapping(columnMapping)

  const resetPreviewState = () => {
    setPreview(null)
    setSelectedKeys([])
    setOldSourceDisabled(false)
    setReceipt(null)
    setMappingRowKey(null)
    setIdentityTarget('')
    setIdentityTargetType('username')
    setShowReceiptDetails(false)
  }

  const resetParsedState = () => {
    setColumns(null)
    setColumnMapping({})
    setMappingOpen(false)
    resetPreviewState()
  }

  const sourceInput = () => ({
    upload: mode === 'upload' ? (upload ?? undefined) : undefined,
    sheetUrl: mode === 'google' ? sheetUrl.trim() || undefined : undefined,
  })

  const handlePreview = async (mapping: CheckinImportColumnMapping = columnMapping) => {
    if (!sourceTimezone || !throughDate || !hasRequiredMapping(mapping) || !hasSource) return
    setLoading(true)
    try {
      const next = await previewCheckinImport({
        source,
        sourceTimezone,
        throughDate,
        ...sourceInput(),
        columnMapping: mapping,
      })
      setPreview(next)
      setSelectedKeys(
        Object.entries(next.default_selection)
          .filter(([, enabled]) => enabled)
          .map(([key]) => key)
      )
      setOldSourceDisabled(false)
      setReceipt(null)
      setMappingRowKey(null)
      setIdentityTarget('')
      setIdentityTargetType('username')
      setShowReceiptDetails(false)
      setMappingOpen(false)
    } catch (error) {
      toastApiError(error, '讀取簽到資料失敗')
    } finally {
      setLoading(false)
    }
  }

  const handleInspect = async () => {
    if (!hasSource) return
    setInspecting(true)
    resetParsedState()
    try {
      const inspected = await inspectCheckinImportColumns(sourceInput())
      const suggestedMapping = inspected.suggested_mapping
      setColumns(inspected)
      setColumnMapping(suggestedMapping)
      if (!hasRequiredMapping(suggestedMapping)) {
        setMappingOpen(true)
        return
      }
      await handlePreview(suggestedMapping)
    } catch (error) {
      toastApiError(error, '讀取來源欄位失敗')
    } finally {
      setInspecting(false)
    }
  }

  const handleApply = async () => {
    if (!preview || !oldSourceDisabled || selectedKeys.length === 0) return
    setApplying(true)
    try {
      const result = await applyCheckinImport(preview.import_id, selectedKeys, true)
      setReceipt(result)
      toast.success(
        result.already_applied
          ? '這批簽到資料先前已匯入'
          : `已轉移 ${result.imported_rows} 位觀眾的簽到累積`
      )
    } catch (error) {
      toastApiError(error, '套用簽到資料失敗')
    } finally {
      setApplying(false)
    }
  }

  const beginIdentityMapping = (row: CheckinImportRow) => {
    setMappingRowKey(row.key)
    setIdentityTarget('')
    setIdentityTargetType('username')
  }

  const handleIdentityMapping = async () => {
    if (!preview || !mappingRowKey || !identityTarget.trim()) return
    setRemapping(true)
    try {
      const next = await remapCheckinImportIdentities(preview.import_id, [
        {
          rowKey: mappingRowKey,
          targetType: identityTargetType,
          value: identityTarget.trim(),
        },
      ])
      const selectableKeys = new Set(
        next.rows
          .filter(row => row.status === 'ready' || row.status === 'review')
          .map(row => row.key)
      )
      setPreview(next)
      setSelectedKeys(current => current.filter(key => selectableKeys.has(key)))
      const mappedRow = next.rows.find(row => row.key === mappingRowKey)
      if (!mappedRow || mappedRow.status === 'unresolved') {
        toast.error(mappedRow?.issues[0] ?? '找不到指定帳號，請重新輸入')
        return
      }
      setMappingRowKey(null)
      setIdentityTarget('')
      toast.success('帳號已驗證，請確認配對結果')
    } catch (error) {
      toastApiError(error, '驗證 Twitch 帳號失敗')
    } finally {
      setRemapping(false)
    }
  }

  const switchMode = (next: InputMode) => {
    setMode(next)
    resetParsedState()
  }

  const updateMapping = (field: CheckinImportCanonicalField, rawIndex: string) => {
    setColumnMapping(current => {
      const next = { ...current }
      if (!rawIndex) delete next[field]
      else next[field] = Number(rawIndex)
      return next
    })
    resetPreviewState()
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="gap-section sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle>轉移舊 Bot 簽到</SheetTitle>
          <SheetDescription>先核對觀眾與簽到資料，確認後再匯入。</SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-card overflow-y-auto px-page pb-page">
          <Alert>
            <Icon icon="fa-solid fa-circle-info" />
            <AlertTitle>匯入前先停用舊 Bot</AlertTitle>
            <AlertDescription>
              已有 Niibot 資料的觀眾不可匯入；確認時若產生衝突，整批停止。
            </AlertDescription>
          </Alert>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="checkin-import-source">來源 Bot</Label>
              <select
                id="checkin-import-source"
                aria-label="簽到資料來源"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={source}
                onChange={event => {
                  setSource(event.target.value)
                  resetPreviewState()
                }}
              >
                <option value="chiwabots">ChiwaBots</option>
                <option value="nightbot">Nightbot</option>
                <option value="streamelements">StreamElements</option>
                <option value="other-bot">其他 Bot</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="checkin-import-timezone">來源時區</Label>
              <Input
                id="checkin-import-timezone"
                aria-label="來源時區"
                value={sourceTimezone}
                onChange={event => {
                  setSourceTimezone(event.target.value)
                  resetPreviewState()
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="checkin-import-through-date">資料截止日</Label>
              <Input
                id="checkin-import-through-date"
                aria-label="資料截止日"
                type="date"
                value={throughDate}
                onChange={event => {
                  setThroughDate(event.target.value)
                  resetPreviewState()
                }}
              />
            </div>
          </div>

          <div className="space-y-3 border-t pt-card">
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant={mode === 'upload' ? 'default' : 'outline'}
                onClick={() => switchMode('upload')}
              >
                上傳檔案
              </Button>
              <Button
                type="button"
                size="sm"
                variant={mode === 'google' ? 'default' : 'outline'}
                onClick={() => switchMode('google')}
              >
                Google Sheets
              </Button>
            </div>
            {mode === 'upload' ? (
              <div className="space-y-2">
                <Label htmlFor="checkin-import-file">CSV、TSV 或 XLSX</Label>
                <Input
                  id="checkin-import-file"
                  aria-label="選擇簽到資料檔案"
                  type="file"
                  accept=".csv,.tsv,.xlsx,text/csv,text/tab-separated-values,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={event => {
                    setUpload(event.target.files?.[0] ?? null)
                    resetParsedState()
                  }}
                />
                <p className="text-label text-muted-foreground">
                  XLSX 讀取第一個可見工作表；公式欄位需先貼成值。最多 10,000 筆。
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="checkin-import-sheet-url">Google Sheets 連結</Label>
                <Input
                  id="checkin-import-sheet-url"
                  aria-label="Google Sheets 連結"
                  type="url"
                  placeholder="https://docs.google.com/spreadsheets/d/.../edit?gid=0"
                  value={sheetUrl}
                  onChange={event => {
                    setSheetUrl(event.target.value)
                    resetParsedState()
                  }}
                />
                <p className="text-label text-muted-foreground">
                  僅支援已開放「知道連結的使用者可查看」或已發布的試算表；私人表格 OAuth 尚未支援。
                </p>
              </div>
            )}
            <details className="text-label text-muted-foreground">
              <summary className="w-fit cursor-pointer select-none font-medium text-foreground">
                格式需求與範例
              </summary>
              <div className="mt-2 space-y-2 pl-3">
                <p>
                  必要：觀眾識別、累積天數、最後簽到。可選：顯示名稱、Twitch
                  ID、連續天數、最後簽到日順位。
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => downloadExample(',', 'csv')}
                  >
                    下載 CSV 範例
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => downloadExample('\t', 'tsv')}
                  >
                    下載 TSV 範例
                  </Button>
                </div>
              </div>
            </details>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                onClick={() => void handleInspect()}
                disabled={inspecting || loading || !hasSource || !sourceTimezone || !throughDate}
              >
                {(inspecting || loading) && <Spinner className="mr-1.5" />}
                {columns ? '重新讀取並預覽' : '讀取並預覽'}
              </Button>
              {columns && !mappingOpen && (
                <Button type="button" variant="outline" onClick={() => setMappingOpen(true)}>
                  調整欄位對應
                </Button>
              )}
            </div>
          </div>

          {columns && mappingOpen && (
            <section className="space-y-3 border-t pt-card" aria-labelledby="checkin-column-map">
              <div>
                <h3 id="checkin-column-map" className="font-medium">
                  對應來源欄位
                </h3>
                <p className="text-label text-muted-foreground">
                  已自動填入可辨識的欄位；只需修正沒有對上的項目。
                </p>
              </div>
              {!mappingReady && (
                <Alert>
                  <Icon icon="fa-solid fa-triangle-exclamation" />
                  <AlertTitle>還需要對應必要欄位</AlertTitle>
                  <AlertDescription>請對應觀眾、累積天數與最後簽到。</AlertDescription>
                </Alert>
              )}
              <ColumnMappingFields
                fields={REQUIRED_MAPPING_FIELDS}
                headers={columns.headers}
                mapping={columnMapping}
                onChange={updateMapping}
              />
              <details>
                <summary className="w-fit cursor-pointer select-none text-sm font-medium">
                  其他欄位（可選）
                </summary>
                <div className="mt-3">
                  <ColumnMappingFields
                    fields={OPTIONAL_MAPPING_FIELDS}
                    headers={columns.headers}
                    mapping={columnMapping}
                    onChange={updateMapping}
                  />
                </div>
              </details>
              <Button
                type="button"
                onClick={() => void handlePreview()}
                disabled={loading || !sourceTimezone || !throughDate || !mappingReady || !hasSource}
              >
                {loading && <Spinner className="mr-1.5" />}
                更新預覽
              </Button>
            </section>
          )}

          {preview && (
            <section
              className="space-y-3 border-t pt-card"
              aria-labelledby="checkin-import-preview"
            >
              <div className="space-y-2">
                <h3 id="checkin-import-preview" className="font-medium">
                  匯入前預覽
                </h3>
                <p className="text-label text-muted-foreground">
                  尚未寫入任何資料。已選 {selectedKeys.length} 筆。
                </p>
                <div className="flex flex-wrap gap-2" aria-label="預覽結果統計">
                  <Badge variant="secondary">可匯入 {counts.ready}</Badge>
                  {counts.unresolved > 0 && (
                    <Badge variant="outline">待配對 {counts.unresolved}</Badge>
                  )}
                  {counts.review > 0 && <Badge variant="outline">待確認 {counts.review}</Badge>}
                  {counts.conflict > 0 && (
                    <Badge variant="outline">資料衝突 {counts.conflict}</Badge>
                  )}
                  {counts.invalid > 0 && <Badge variant="outline">格式錯誤 {counts.invalid}</Badge>}
                </div>
              </div>
              <div className="overflow-hidden rounded-md border text-sm">
                <div className="bg-muted/50 hidden grid-cols-[2rem_minmax(10rem,1.3fr)_minmax(7rem,.7fr)_7.5rem_minmax(10rem,1fr)] gap-3 px-3 py-2 text-label font-medium text-muted-foreground md:grid">
                  <span aria-hidden="true" />
                  <span>觀眾</span>
                  <span>簽到紀錄</span>
                  <span>最後簽到</span>
                  <span>狀態</span>
                </div>
                <div className="divide-y">
                  {sortedRows.slice(0, 100).map(row => {
                    const name = rowName(row)
                    const canSelect = row.status === 'ready' || row.status === 'review'
                    const source = sourceIdentity(row)
                    const mappingOpenForRow = mappingRowKey === row.key
                    return (
                      <div
                        key={row.key}
                        className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 gap-y-2 px-3 py-3 md:grid-cols-[2rem_minmax(10rem,1.3fr)_minmax(7rem,.7fr)_7.5rem_minmax(10rem,1fr)] md:items-start"
                      >
                        <div className="pt-0.5">
                          <input
                            type="checkbox"
                            aria-label={`選取 ${name}`}
                            checked={selected.has(row.key)}
                            disabled={!canSelect}
                            onChange={event =>
                              setSelectedKeys(current =>
                                event.target.checked
                                  ? [...current, row.key]
                                  : current.filter(key => key !== row.key)
                              )
                            }
                          />
                        </div>

                        <div className="min-w-0">
                          <p className="truncate font-medium">{name}</p>
                          {showUsername(row) && (
                            <p className="truncate text-label text-muted-foreground">
                              @{row.username}
                            </p>
                          )}
                          {row.identity_resolution === 'manual' && (
                            <p className="truncate text-label text-muted-foreground">
                              來源 {source}
                            </p>
                          )}
                        </div>

                        <div className="col-start-2 md:col-start-auto">
                          <span className="text-label text-muted-foreground md:hidden">紀錄：</span>
                          <span className="tabular-nums">
                            {row.total_days === null ? '—' : `累積 ${row.total_days} 天`}
                          </span>
                          {row.current_streak !== null && (
                            <span className="block text-label text-muted-foreground tabular-nums">
                              連續 {row.current_streak} 天
                            </span>
                          )}
                        </div>

                        <div className="col-start-2 tabular-nums md:col-start-auto">
                          <span className="text-label text-muted-foreground md:hidden">
                            最後簽到：
                          </span>
                          {row.last_checkin_date ?? '—'}
                        </div>

                        <div className="col-start-2 space-y-1.5 md:col-start-auto">
                          <Badge variant="outline">{STATUS_LABELS[row.status]}</Badge>
                          {row.issues.length > 0 && (
                            <p
                              className={
                                row.status === 'review'
                                  ? 'text-label text-muted-foreground'
                                  : 'text-label text-destructive'
                              }
                            >
                              {row.issues.join('；')}
                            </p>
                          )}
                          {row.status === 'unresolved' && !mappingOpenForRow && (
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => beginIdentityMapping(row)}
                              aria-label={`指定 ${source.replace(/^@/, '')} 的現行帳號`}
                            >
                              指定帳號
                            </Button>
                          )}
                        </div>

                        {mappingOpenForRow && (
                          <div className="col-span-full ml-8 space-y-3 rounded-md bg-muted/40 p-3 md:ml-0">
                            <div className="flex flex-wrap items-end gap-2">
                              <div className="min-w-[13rem] flex-1 space-y-1.5">
                                <Label htmlFor={`identity-target-${row.key}`}>
                                  {identityTargetType === 'username'
                                    ? '目前 Twitch 帳號'
                                    : 'Twitch ID'}
                                </Label>
                                <Input
                                  id={`identity-target-${row.key}`}
                                  aria-label={
                                    identityTargetType === 'username'
                                      ? '目前 Twitch 帳號'
                                      : 'Twitch ID'
                                  }
                                  value={identityTarget}
                                  inputMode={identityTargetType === 'user_id' ? 'numeric' : 'text'}
                                  maxLength={identityTargetType === 'user_id' ? 32 : 25}
                                  autoComplete="off"
                                  onChange={event => setIdentityTarget(event.target.value)}
                                />
                              </div>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                  setIdentityTargetType(current =>
                                    current === 'username' ? 'user_id' : 'username'
                                  )
                                  setIdentityTarget('')
                                }}
                              >
                                {identityTargetType === 'username' ? '改用 Twitch ID' : '改用帳號'}
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                disabled={!identityTarget.trim() || remapping}
                                onClick={() => void handleIdentityMapping()}
                              >
                                {remapping && <Spinner className="mr-1.5" />}
                                驗證配對
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                disabled={remapping}
                                onClick={() => setMappingRowKey(null)}
                              >
                                取消
                              </Button>
                            </div>
                            <p className="text-label text-muted-foreground">
                              來源 {source}。Niibot 會向 Twitch 驗證，不會直接採用輸入值。
                            </p>
                          </div>
                        )}

                        {(row.daily_order !== null || row.source_row > 0) && (
                          <details className="col-span-full ml-8 text-label text-muted-foreground md:ml-0">
                            <summary className="w-fit cursor-pointer select-none text-foreground">
                              來源資料
                            </summary>
                            <p className="mt-1">
                              第 {row.source_row} 列
                              {row.daily_order !== null
                                ? ` · 最後簽到日第 ${row.daily_order} 位`
                                : ''}
                            </p>
                          </details>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
              {preview.rows.length > 100 && (
                <p className="text-label text-muted-foreground">
                  畫面先顯示前 100 筆；本批共有 {preview.rows.length} 筆。
                </p>
              )}
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  aria-label="我已停用舊 Bot 的簽到"
                  checked={oldSourceDisabled}
                  onChange={event => setOldSourceDisabled(event.target.checked)}
                />
                <span>我已停用舊 Bot 的簽到，並了解匯入只增加累積值、不補發歷史卡片。</span>
              </label>
            </section>
          )}

          {receipt && (
            <Alert>
              <Icon icon="fa-solid fa-circle-check" />
              <AlertTitle>轉移完成</AlertTitle>
              <AlertDescription className="space-y-2">
                <p>
                  已匯入 {receipt.imported_rows} 位觀眾
                  {receipt.already_applied ? '；這批資料先前已處理，未重複加總。' : '。'}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowReceiptDetails(current => !current)}
                >
                  {showReceiptDetails ? '收起技術資訊' : '查看技術資訊'}
                </Button>
                {showReceiptDetails && (
                  <p className="break-all text-label text-muted-foreground">
                    匯入批次：{receipt.batch_id}
                  </p>
                )}
              </AlertDescription>
            </Alert>
          )}
        </div>

        <SheetFooter className="shrink-0 flex-row justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            關閉
          </Button>
          {preview && !receipt && (
            <Button
              onClick={() => void handleApply()}
              disabled={selectedKeys.length === 0 || !oldSourceDisabled || applying}
            >
              {applying && <Spinner className="mr-1.5" />}
              確認匯入 {selectedKeys.length} 筆
            </Button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

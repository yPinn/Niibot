import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  applyCheckinImport,
  type CheckinImportApplyResult,
  type CheckinImportCanonicalField,
  type CheckinImportColumnMapping,
  type CheckinImportColumns,
  type CheckinImportPreview,
  inspectCheckinImportColumns,
  previewCheckinImport,
} from '@/api/checkin'
import { Icon, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertTitle,
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
  review: '需確認',
  invalid: '欄位值無效',
  unresolved: '找不到帳號',
  conflict: '已有資料',
}

type MappingField = {
  field: CheckinImportCanonicalField
  label: string
  hint: string
}

const REQUIRED_MAPPING_FIELDS: ReadonlyArray<MappingField> = [
  { field: 'username', label: 'Username', hint: '與 Twitch User ID 擇一' },
  { field: 'platform_user_id', label: 'Twitch User ID', hint: '與 Username 擇一' },
  { field: 'total_days', label: 'Count', hint: '必要' },
  { field: 'last_checkin_date', label: 'LastDate', hint: '必要，YYYY-MM-DD' },
]

const OPTIONAL_MAPPING_FIELDS: ReadonlyArray<MappingField> = [
  { field: 'display_name', label: 'DisplayName', hint: '可選' },
  { field: 'current_streak', label: 'Streak', hint: '可選' },
  { field: 'daily_order', label: 'TodayOrder', hint: '可選，只作稽核' },
]

const today = () => new Date().toISOString().slice(0, 10)

function hasRequiredMapping(mapping: CheckinImportColumnMapping) {
  return (
    (mapping.username !== undefined || mapping.platform_user_id !== undefined) &&
    mapping.total_days !== undefined &&
    mapping.last_checkin_date !== undefined
  )
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

  const selected = useMemo(() => new Set(selectedKeys), [selectedKeys])
  const counts = useMemo(() => {
    const result = { ready: 0, review: 0, invalid: 0, unresolved: 0, conflict: 0 }
    for (const row of preview?.rows ?? []) result[row.status] += 1
    return result
  }, [preview])

  const hasSource = mode === 'upload' ? Boolean(upload) : Boolean(sheetUrl.trim())
  const mappingReady = hasRequiredMapping(columnMapping)

  const resetPreviewState = () => {
    setPreview(null)
    setSelectedKeys([])
    setOldSourceDisabled(false)
    setReceipt(null)
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
          <SheetDescription>
            先預覽累積天數、最後日期與連續天數，確認後才會正式匯入。
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-card overflow-y-auto px-page pb-page">
          <Alert>
            <Icon icon="fa-solid fa-circle-info" />
            <AlertTitle>正式匯入前請停用舊 Bot</AlertTitle>
            <AlertDescription>
              同一位觀眾若已有 Niibot 簽到或轉移資料，整批會停止，不會自動相加或覆蓋。
            </AlertDescription>
          </Alert>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="checkin-import-source">來源</Label>
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
                  必要欄位：Username 或 Twitch User
                  ID、Count、LastDate。可選：DisplayName、Streak、TodayOrder。
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
                  <AlertDescription>
                    請指定觀眾帳號、Count 與 LastDate，完成後即可建立預覽。
                  </AlertDescription>
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
              <div>
                <h3 id="checkin-import-preview" className="font-medium">
                  匯入前預覽
                </h3>
                <p className="text-label text-muted-foreground">
                  尚未寫入任何資料。已選 {selectedKeys.length}／{counts.ready} 筆可匯入資料；需確認{' '}
                  {counts.review}、欄位值無效 {counts.invalid}、找不到帳號 {counts.unresolved}
                  、已有資料 {counts.conflict}。
                </p>
              </div>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="p-2">選取</th>
                      <th className="p-2">觀眾</th>
                      <th className="p-2">累積</th>
                      <th className="p-2">最後日期</th>
                      <th className="p-2">連續</th>
                      <th className="p-2">狀態</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.slice(0, 100).map(row => (
                      <tr key={row.key} className="border-t">
                        <td className="p-2">
                          <input
                            type="checkbox"
                            aria-label={`選取 ${row.display_name ?? row.username ?? row.user_id ?? `第 ${row.source_row} 列`}`}
                            checked={selected.has(row.key)}
                            disabled={row.status !== 'ready'}
                            onChange={event =>
                              setSelectedKeys(current =>
                                event.target.checked
                                  ? [...current, row.key]
                                  : current.filter(key => key !== row.key)
                              )
                            }
                          />
                        </td>
                        <td className="p-2">{row.display_name ?? row.username ?? row.user_id}</td>
                        <td className="p-2">{row.total_days ?? '—'}</td>
                        <td className="p-2">{row.last_checkin_date ?? '—'}</td>
                        <td className="p-2">{row.current_streak ?? '—'}</td>
                        <td className="p-2">
                          {STATUS_LABELS[row.status]}
                          {row.issues.length > 0 && (
                            <span className="block text-xs text-destructive">
                              {row.issues.join('；')}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
              <AlertDescription>
                已處理 {receipt.imported_rows} 位觀眾；批次編號：{receipt.batch_id}
                {receipt.already_applied ? '（先前已套用，本次未重複加總）' : ''}
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

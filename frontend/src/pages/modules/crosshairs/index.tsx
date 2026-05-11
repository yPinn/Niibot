import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  createCrosshair,
  type Crosshair,
  CROSSHAIR_GAME_LABELS,
  type CrosshairCreate,
  type CrosshairGame,
  type CrosshairWithChannel,
  deleteCrosshair,
  getAllPublicCrosshairs,
  getCrosshairs,
  getPublicCrosshairs,
  recordCrosshairCopy,
  updateCrosshair,
} from '@/api/crosshairs'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Icon,
  Input,
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetSection,
  SheetTitle,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { copyToClipboard } from '@/lib/clipboard'

import { CrosshairAdjustSheet } from './CrosshairAdjustSheet'
import { CrosshairCardBase } from './CrosshairCardBase'
import { CrosshairDetailPreview, CrosshairPreview } from './CrosshairPreview'
import { ShootingRange } from './ShootingRange'

function copyCode(code: string, id?: string) {
  copyToClipboard(code, '已複製準星代碼')
  if (id) recordCrosshairCopy(id)
}

interface FormState {
  game: CrosshairGame
  name: string
  code: string
  description: string
}

const DEFAULT_FORM: FormState = { game: 'valorant', name: '', code: '', description: '' }

export default function CrosshairModule() {
  useDocumentTitle('Crosshair Repo')

  // My crosshairs state
  const [crosshairs, setCrosshairs] = useState<Crosshair[]>([])
  const crosshairsRef = useRef(crosshairs)
  useEffect(() => {
    crosshairsRef.current = crosshairs
  }, [crosshairs])
  const [loadingMine, setLoadingMine] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Crosshair | null>(null)

  // Sheet state
  const [sheetOpen, setSheetOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)

  // Browse state
  const [allPublic, setAllPublic] = useState<CrosshairWithChannel[]>([])
  const [allPublicLoading, setAllPublicLoading] = useState(true)
  const [browseInput, setBrowseInput] = useState('')
  const [browseResults, setBrowseResults] = useState<CrosshairWithChannel[] | null>(null)
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState<string | null>(null)

  // Adjust sheet
  const [adjustTarget, setAdjustTarget] = useState<Crosshair | null>(null)

  // Detail sheet (browse)
  const [detailTarget, setDetailTarget] = useState<CrosshairWithChannel | null>(null)

  useEffect(() => {
    let cancelled = false
    getCrosshairs()
      .then(data => {
        if (!cancelled) setCrosshairs(data)
      })
      .catch(() => toast.error('無法載入準星'))
      .finally(() => {
        if (!cancelled) setLoadingMine(false)
      })
    getAllPublicCrosshairs()
      .then(data => {
        if (!cancelled) setAllPublic(data)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setAllPublicLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function openAdd() {
    setEditingId(null)
    setForm(DEFAULT_FORM)
    setSheetOpen(true)
  }

  const openAdjust = useCallback((c: Crosshair) => setAdjustTarget(c), [])

  const saveCrosshairCode = useCallback(async (target: Crosshair, code: string) => {
    try {
      const updated = await updateCrosshair(target.id, {
        game: target.game,
        name: target.name,
        code,
        description: target.description ?? null,
      })
      setCrosshairs(cs => cs.map(c => (c.id === target.id ? updated : c)))
      toast.success('已更新準星')
    } catch {
      toast.error('儲存失敗')
    }
  }, [])

  const handleAdjustSave = useCallback(
    (code: string) => {
      if (adjustTarget) saveCrosshairCode(adjustTarget, code)
    },
    [adjustTarget, saveCrosshairCode]
  )

  const handleRangeSave = useCallback(
    (id: string, code: string) => {
      const target = crosshairsRef.current.find(c => c.id === id)
      if (target) saveCrosshairCode(target, code)
    },
    [saveCrosshairCode]
  )

  const openEdit = useCallback((c: Crosshair) => {
    setEditingId(c.id)
    setForm({ game: c.game, name: c.name, code: c.code, description: c.description ?? '' })
    setSheetOpen(true)
  }, [])

  async function handleSave() {
    if (!form.name.trim() || !form.code.trim()) {
      toast.error('名稱和代碼不能為空')
      return
    }
    setSaving(true)
    const payload: CrosshairCreate = {
      game: form.game,
      name: form.name.trim(),
      code: form.code.trim(),
      description: form.description.trim() || null,
    }
    try {
      if (editingId) {
        const updated = await updateCrosshair(editingId, payload)
        setCrosshairs(cs => cs.map(c => (c.id === editingId ? updated : c)))
        toast.success('已更新準星')
      } else {
        const created = await createCrosshair(payload)
        setCrosshairs(cs => [...cs, created])
        toast.success('已新增準星')
      }
      setSheetOpen(false)
    } catch {
      toast.error('儲存失敗')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(c: Crosshair) {
    setDeletingId(c.id)
    try {
      await deleteCrosshair(c.id)
      setCrosshairs(cs => cs.filter(x => x.id !== c.id))
      toast.success('已刪除準星')
    } catch {
      toast.error('刪除失敗')
    } finally {
      setDeletingId(null)
      setDeleteTarget(null)
    }
  }

  async function handleBrowse(e: React.FormEvent) {
    e.preventDefault()
    const un = browseInput.trim()
    if (!un) {
      setBrowseResults(null)
      setBrowseError(null)
      return
    }
    setBrowseLoading(true)
    setBrowseError(null)
    try {
      const data = await getPublicCrosshairs(un)
      const withChannel: CrosshairWithChannel[] = data.crosshairs.map(c => ({
        ...c,
        channel_name: data.channel.display_name ?? un,
      }))
      setBrowseResults(withChannel)
    } catch {
      setBrowseError(`找不到使用者「${un}」或無法取得準星資料`)
      setBrowseResults(null)
    } finally {
      setBrowseLoading(false)
    }
  }

  return (
    <>
      <PageMain>
        <PageHeader title="Crosshair Repo" description="管理你的準星代碼，或查看公開的準星收藏" />
        <Tabs defaultValue="mine" className="flex-1 min-h-0">
          <TabsList>
            <TabsTrigger value="mine">我的</TabsTrigger>
            <TabsTrigger value="browse">公開</TabsTrigger>
            <TabsTrigger value="range">靶場</TabsTrigger>
          </TabsList>

          <TabsContent value="mine" className="mt-section overflow-y-auto">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>我的準星</CardTitle>
                <Button size="sm" onClick={openAdd}>
                  <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1 size-3.5" />
                  新增準星
                </Button>
              </CardHeader>
              <CardContent>
                {loadingMine ? (
                  <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Skeleton key={i} className="aspect-square rounded-xl" />
                    ))}
                  </div>
                ) : crosshairs.length === 0 ? (
                  <p className="py-12 text-center text-muted-foreground">
                    還沒有準星，點擊「新增準星」開始收藏
                  </p>
                ) : (
                  <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                    {crosshairs.map(c => (
                      <MyCrosshairCard
                        key={c.id}
                        crosshair={c}
                        isDeleting={deletingId === c.id}
                        onEdit={openEdit}
                        onAdjust={openAdjust}
                        onDelete={setDeleteTarget}
                        onCopy={copyCode}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="browse" className="mt-section overflow-y-auto">
            <Card>
              <CardHeader>
                <CardTitle>公開準星</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <form onSubmit={handleBrowse} className="flex gap-element">
                  <Input
                    placeholder="輸入 Twitch 帳號篩選..."
                    value={browseInput}
                    onChange={e => setBrowseInput(e.target.value)}
                    className="max-w-xs"
                  />
                  <Button type="submit" variant="secondary" disabled={browseLoading}>
                    {browseLoading ? '搜尋中...' : browseInput.trim() ? '搜尋' : '顯示全部'}
                  </Button>
                </form>

                {browseError && <p className="text-sm text-destructive">{browseError}</p>}

                {(() => {
                  const displayed = browseResults ?? allPublic
                  if (allPublicLoading && browseResults === null) {
                    return (
                      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                        {Array.from({ length: 8 }).map((_, i) => (
                          <Skeleton key={i} className="aspect-square rounded-xl" />
                        ))}
                      </div>
                    )
                  }
                  if (displayed.length === 0) {
                    return (
                      <p className="py-12 text-center text-muted-foreground">
                        {browseResults !== null ? '此使用者尚無準星' : '目前尚無任何準星'}
                      </p>
                    )
                  }
                  return (
                    <>
                      <p className="text-sm text-muted-foreground">
                        {browseResults !== null
                          ? `${browseResults[0]?.channel_name ?? browseInput} 的準星收藏（${browseResults.length} 個）`
                          : `最新收藏（共 ${displayed.length} 個）`}
                      </p>
                      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5">
                        {displayed.map(c => (
                          <BrowseCrosshairCard
                            key={c.id}
                            crosshair={c}
                            onSelect={setDetailTarget}
                          />
                        ))}
                      </div>
                    </>
                  )
                })()}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="range" className="mt-section flex flex-col min-h-0">
            <ShootingRange crosshairs={crosshairs} onSave={handleRangeSave} />
          </TabsContent>
        </Tabs>
      </PageMain>

      <CrosshairAdjustSheet
        key={adjustTarget?.id ?? ''}
        open={!!adjustTarget}
        onOpenChange={open => !open && setAdjustTarget(null)}
        initialCode={adjustTarget?.code ?? ''}
        onSave={handleAdjustSave}
      />

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" className="sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{editingId ? '編輯準星' : '新增準星'}</SheetTitle>
          </SheetHeader>

          <SheetSection>
            <div className="flex justify-center py-element">
              <div className="flex items-center justify-center rounded-2xl bg-zinc-500 p-3">
                <CrosshairPreview
                  game={form.game}
                  code={form.code || '0;P;0l;4;0o;2;0t;2'}
                  size="lg"
                />
              </div>
            </div>
          </SheetSection>

          <SheetSection title="名稱">
            <Input
              placeholder="例如：主要準星"
              value={form.name}
              maxLength={100}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            />
          </SheetSection>

          <SheetSection title="準星代碼">
            <Textarea
              placeholder="貼上準星代碼..."
              value={form.code}
              className="font-mono text-sm"
              rows={3}
              onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
            />
          </SheetSection>

          <SheetSection title="備註（選填）">
            <Textarea
              placeholder="描述這個準星的特色..."
              value={form.description}
              rows={2}
              maxLength={500}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </SheetSection>

          <SheetFooter>
            <Button onClick={handleSave} disabled={saving} className="w-full">
              {saving ? '儲存中...' : '儲存'}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <Sheet open={!!detailTarget} onOpenChange={open => !open && setDetailTarget(null)}>
        <SheetContent side="right" className="sm:max-w-md">
          {detailTarget && (
            <>
              <SheetHeader>
                <div className="flex items-center gap-element">
                  <Badge variant="secondary">{CROSSHAIR_GAME_LABELS[detailTarget.game]}</Badge>
                </div>
                <SheetTitle className="mt-1">{detailTarget.name}</SheetTitle>
              </SheetHeader>

              <SheetSection>
                <CrosshairDetailPreview game={detailTarget.game} code={detailTarget.code} />
              </SheetSection>

              <SheetSection title="準星代碼">
                <div className="flex items-center gap-element">
                  <code className="flex-1 break-all rounded bg-muted px-3 py-2 font-mono text-sm">
                    {detailTarget.code}
                  </code>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => copyCode(detailTarget.code, detailTarget.id)}
                  >
                    <Icon icon="fa-solid fa-copy" wrapperClassName="size-4" />
                  </Button>
                </div>
              </SheetSection>

              {detailTarget.description && (
                <SheetSection title="備註">
                  <p className="text-sm text-muted-foreground">{detailTarget.description}</p>
                </SheetSection>
              )}
            </>
          )}
        </SheetContent>
      </Sheet>

      <AlertDialog open={!!deleteTarget} onOpenChange={open => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>確定要刪除嗎？</AlertDialogTitle>
            <AlertDialogDescription>
              刪除「{deleteTarget?.name}」後無法復原。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteTarget && handleDelete(deleteTarget)}
            >
              刪除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

const MyCrosshairCard = memo(function MyCrosshairCard({
  crosshair,
  isDeleting,
  onEdit,
  onAdjust,
  onDelete,
  onCopy,
}: {
  crosshair: Crosshair
  isDeleting: boolean
  onEdit: (c: Crosshair) => void
  onAdjust: (c: Crosshair) => void
  onDelete: (c: Crosshair) => void
  onCopy: (code: string) => void
}) {
  return (
    <CrosshairCardBase
      crosshair={crosshair}
      onCopy={onCopy}
      footer={
        <div className="flex justify-end pr-element pb-element">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => onAdjust(crosshair)}
            title="調整準星"
          >
            <Icon icon="fa-solid fa-sliders" />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => onEdit(crosshair)} title="編輯">
            <Icon icon="fa-solid fa-pen" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-destructive hover:text-destructive"
            disabled={isDeleting}
            onClick={() => onDelete(crosshair)}
            title="刪除"
          >
            <Icon icon="fa-solid fa-trash" />
          </Button>
        </div>
      }
    />
  )
})

const BrowseCrosshairCard = memo(function BrowseCrosshairCard({
  crosshair,
  onSelect,
}: {
  crosshair: CrosshairWithChannel
  onSelect: (c: CrosshairWithChannel) => void
}) {
  return (
    <CrosshairCardBase
      crosshair={crosshair}
      onCopy={code => copyCode(code, crosshair.id)}
      onCardClick={() => onSelect(crosshair)}
      channelName={crosshair.channel_name}
      copyCount={crosshair.copy_count}
    />
  )
})

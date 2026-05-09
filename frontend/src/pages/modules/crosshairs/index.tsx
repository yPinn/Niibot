import { useEffect, useState } from 'react'
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

import { CrosshairPreview } from './CrosshairPreview'

const GAME_LABELS = CROSSHAIR_GAME_LABELS

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

  function openEdit(c: Crosshair) {
    setEditingId(c.id)
    setForm({ game: c.game, name: c.name, code: c.code, description: c.description ?? '' })
    setSheetOpen(true)
  }

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

  function copyCode(code: string) {
    copyToClipboard(code, '已複製準星代碼')
  }

  return (
    <>
      <PageMain>
        <PageHeader title="Crosshair Repo" description="管理你的準星代碼，或瀏覽其他實況主的收藏" />
        <Tabs defaultValue="mine">
          <TabsList>
            <TabsTrigger value="mine">我的準星</TabsTrigger>
            <TabsTrigger value="browse">瀏覽他人</TabsTrigger>
          </TabsList>

          {/* ── 我的準星 ── */}
          <TabsContent value="mine" className="mt-4">
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
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <Skeleton key={i} className="h-48 rounded-xl" />
                    ))}
                  </div>
                ) : crosshairs.length === 0 ? (
                  <p className="py-12 text-center text-muted-foreground">
                    還沒有準星，點擊「新增準星」開始收藏
                  </p>
                ) : (
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                    {crosshairs.map(c => (
                      <MyCrosshairCard
                        key={c.id}
                        crosshair={c}
                        isDeleting={deletingId === c.id}
                        onEdit={() => openEdit(c)}
                        onDelete={() => setDeleteTarget(c)}
                        onCopy={() => copyCode(c.code)}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── 瀏覽他人 ── */}
          <TabsContent value="browse" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>瀏覽他人的準星</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <form onSubmit={handleBrowse} className="flex gap-2">
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
                      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                        {Array.from({ length: 8 }).map((_, i) => (
                          <Skeleton key={i} className="h-48 rounded-xl" />
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
                      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                        {displayed.map(c => (
                          <BrowseCrosshairCard
                            key={c.id}
                            crosshair={c}
                            onCopy={() => copyCode(c.code)}
                            onClick={() => setDetailTarget(c)}
                          />
                        ))}
                      </div>
                    </>
                  )
                })()}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </PageMain>

      {/* ── Add / Edit Sheet ── */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" className="sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{editingId ? '編輯準星' : '新增準星'}</SheetTitle>
          </SheetHeader>

          <SheetSection>
            <div className="flex justify-center py-2">
              <CrosshairPreview
                game={form.game}
                code={form.code || '0;P;0l;4;0o;2;0t;2'}
                size="lg"
              />
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

      {/* ── Browse detail Sheet ── */}
      <Sheet open={!!detailTarget} onOpenChange={open => !open && setDetailTarget(null)}>
        <SheetContent side="right" className="sm:max-w-md">
          {detailTarget && (
            <>
              <SheetHeader>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{GAME_LABELS[detailTarget.game]}</Badge>
                </div>
                <SheetTitle className="mt-1">{detailTarget.name}</SheetTitle>
              </SheetHeader>

              <SheetSection>
                <div className="flex justify-center py-4">
                  <CrosshairPreview game={detailTarget.game} code={detailTarget.code} size="lg" />
                </div>
              </SheetSection>

              <SheetSection title="準星代碼">
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all rounded bg-muted px-3 py-2 font-mono text-sm">
                    {detailTarget.code}
                  </code>
                  <Button variant="outline" size="icon" onClick={() => copyCode(detailTarget.code)}>
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

      {/* ── Delete confirm ── */}
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

// ── Sub-components ──

function MyCrosshairCard({
  crosshair,
  isDeleting,
  onEdit,
  onDelete,
  onCopy,
}: {
  crosshair: Crosshair
  isDeleting: boolean
  onEdit: () => void
  onDelete: () => void
  onCopy: () => void
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="flex flex-col items-center gap-2 p-3">
        <CrosshairPreview game={crosshair.game} code={crosshair.code} size="sm" />
        <div className="w-full text-center">
          <p className="truncate text-sm font-medium">{crosshair.name}</p>
          <Badge variant="secondary" className="mt-0.5 text-xs">
            {GAME_LABELS[crosshair.game] ?? crosshair.game}
          </Badge>
        </div>
        <div className="flex w-full items-center gap-1">
          <code className="min-w-0 flex-1 truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
            {crosshair.code}
          </code>
          <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" onClick={onCopy}>
            <Icon icon="fa-solid fa-copy" wrapperClassName="size-3" />
          </Button>
        </div>
        <div className="flex w-full gap-1.5">
          <Button variant="outline" size="sm" className="h-7 flex-1 text-xs" onClick={onEdit}>
            編輯
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 flex-1 text-xs text-destructive hover:text-destructive"
            disabled={isDeleting}
            onClick={onDelete}
          >
            刪除
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function BrowseCrosshairCard({
  crosshair,
  onCopy,
  onClick,
}: {
  crosshair: CrosshairWithChannel
  onCopy: () => void
  onClick: () => void
}) {
  return (
    <Card
      className="cursor-pointer overflow-hidden transition-shadow hover:shadow-md"
      onClick={onClick}
    >
      <CardContent className="flex flex-col items-center gap-2 p-3">
        <CrosshairPreview game={crosshair.game} code={crosshair.code} size="sm" />
        <div className="w-full text-center">
          <p className="truncate text-sm font-medium">{crosshair.name}</p>
          <p className="truncate text-xs text-muted-foreground">{crosshair.channel_name}</p>
          <Badge variant="secondary" className="mt-0.5 text-xs">
            {GAME_LABELS[crosshair.game] ?? crosshair.game}
          </Badge>
        </div>
        <div
          className="flex w-full items-center gap-1"
          onClick={e => {
            e.stopPropagation()
            onCopy()
          }}
        >
          <code className="min-w-0 flex-1 truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
            {crosshair.code}
          </code>
          <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" asChild>
            <span>
              <Icon icon="fa-solid fa-copy" wrapperClassName="size-3" />
            </span>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

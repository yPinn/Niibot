import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  activateRoleplayRevision,
  archiveRoleplaySet,
  exportRoleplayRevision,
  getRoleplaySet,
  listRoleplaySets,
  type RoleplayImportResult,
  type RoleplaySet,
  type RoleplaySetSummary,
} from '@/api/roleplay'
import { Icon, Spinner } from '@/components/primitives'
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
  CARD_HEADER_STACK_ON_MOBILE,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Skeleton,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

import { RoleplayImportDialog } from './RoleplayImportDialog'
import { RoleplayWizard } from './RoleplayWizard'

type AssistantMode = 'persona' | 'roleplay'

interface RoleplayWorkspaceProps {
  channelId: string
  assistantMode: AssistantMode
  activeRevisionId: number | null
  onModeChange: (mode: AssistantMode, revisionId: number | null) => void
}

export function RoleplayWorkspace({
  channelId,
  assistantMode,
  activeRevisionId,
  onModeChange,
}: RoleplayWorkspaceProps) {
  const [sets, setSets] = useState<RoleplaySetSummary[]>([])
  const [editing, setEditing] = useState<RoleplaySet | 'new' | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [exportTarget, setExportTarget] = useState<RoleplaySetSummary | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<RoleplaySetSummary | null>(null)
  const [exporting, setExporting] = useState(false)
  const importTriggerRef = useRef<HTMLButtonElement>(null)

  const loadSets = useCallback(async () => {
    setLoading(true)
    try {
      setSets(await listRoleplaySets(channelId))
    } catch (error) {
      toastApiError(error, '載入故事角色失敗')
    } finally {
      setLoading(false)
    }
  }, [channelId])

  useEffect(() => {
    let active = true
    listRoleplaySets(channelId)
      .then(result => active && setSets(result))
      .catch(error => active && toastApiError(error, '載入故事角色失敗'))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [channelId])

  async function editSet(summary: RoleplaySetSummary) {
    setBusyId(summary.id)
    try {
      setEditing(await getRoleplaySet(channelId, summary.id))
    } catch (error) {
      toastApiError(error, '載入角色草稿失敗')
    } finally {
      setBusyId(null)
    }
  }

  async function activate(summary: RoleplaySetSummary) {
    if (!summary.published) return
    setBusyId(summary.id)
    try {
      const mode = await activateRoleplayRevision(channelId, summary.id, summary.published.id)
      onModeChange(mode.assistant_mode, mode.active_roleplay_revision_id)
      toast.success(`已開始使用「${summary.name}」`)
    } catch (error) {
      toastApiError(error, '切換故事角色失敗')
    } finally {
      setBusyId(null)
    }
  }

  async function archive(summary: RoleplaySetSummary) {
    setBusyId(summary.id)
    try {
      await archiveRoleplaySet(channelId, summary.id)
      setSets(current => current.filter(item => item.id !== summary.id))
      setArchiveTarget(null)
      toast.success('故事角色已封存')
    } catch (error) {
      toastApiError(error, '封存故事角色失敗')
    } finally {
      setBusyId(null)
    }
  }

  async function downloadExport() {
    if (!exportTarget?.published) return
    setExporting(true)
    let browserUrl: string | null = null
    try {
      const download = await exportRoleplayRevision(
        channelId,
        exportTarget.id,
        exportTarget.published.id
      )
      browserUrl = URL.createObjectURL(download.blob)
      const anchor = document.createElement('a')
      anchor.href = browserUrl
      anchor.download = download.filename
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
      setExportTarget(null)
      toast.success('角色設定集已下載')
    } catch (error) {
      toastApiError(error, '下載角色設定集失敗')
    } finally {
      if (browserUrl) URL.revokeObjectURL(browserUrl)
      setExporting(false)
    }
  }

  function handleImported(result: RoleplayImportResult) {
    setSets(current => {
      const remaining = current.filter(item => item.id !== result.roleplay_set.id)
      return [result.roleplay_set, ...remaining]
    })
    if (result.mode === 'copy') {
      setEditing(result.roleplay_set)
      toast.success('已複製角色設定，可以接著修改')
      return
    }
    onModeChange('roleplay', result.active_roleplay_revision_id)
    toast.success(
      result.reused
        ? `已切換到現有的「${result.roleplay_set.name}」`
        : `已匯入並開始使用「${result.roleplay_set.name}」`
    )
  }

  function mergeSaved(saved: RoleplaySet) {
    setSets(current => {
      const next = current.filter(item => item.id !== saved.id)
      return [saved, ...next]
    })
    setEditing(saved)
  }

  if (editing) {
    return (
      <RoleplayWizard
        channelId={channelId}
        initialSet={editing === 'new' ? null : editing}
        onCancel={() => {
          setEditing(null)
          void loadSets()
        }}
        onSaved={mergeSaved}
        onModeChange={onModeChange}
      />
    )
  }

  return (
    <>
      <Card>
        <CardHeader className={CARD_HEADER_STACK_ON_MOBILE}>
          <div>
            <CardTitle>故事角色</CardTitle>
            <CardDescription className="mt-1">
              每個角色都會記下作品範圍、故事時間點，以及角色知道與不知道的事；最多建立 5 組。
            </CardDescription>
          </div>
          {!loading && sets.length > 0 && (
            <CardAction className="flex flex-wrap gap-2 max-sm:col-start-1 max-sm:row-start-auto max-sm:justify-self-start">
              <Button
                ref={importTriggerRef}
                variant="outline"
                size="sm"
                onClick={() => setImportOpen(true)}
              >
                <Icon icon="fa-solid fa-file-import" className="mr-1.5" />
                匯入角色設定集
              </Button>
              <Button size="sm" onClick={() => setEditing('new')} disabled={sets.length >= 5}>
                <Icon icon="fa-solid fa-plus" className="mr-1.5" />
                建立故事角色
              </Button>
            </CardAction>
          )}
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3" aria-label="正在載入故事角色">
              {Array.from({ length: 2 }).map((_, index) => (
                <Skeleton key={index} className="h-24 w-full rounded-lg" />
              ))}
            </div>
          ) : sets.length === 0 ? (
            <Empty className="border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Icon icon="fa-solid fa-user" />
                </EmptyMedia>
                <EmptyTitle>還沒有故事角色</EmptyTitle>
                <EmptyDescription>
                  跟著七個步驟，從作品範圍和人物小傳開始，建立第一位可在聊天室使用的角色。
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Button onClick={() => setEditing('new')}>建立故事角色</Button>
                  <Button
                    ref={importTriggerRef}
                    variant="outline"
                    onClick={() => setImportOpen(true)}
                  >
                    匯入角色設定集
                  </Button>
                </div>
              </EmptyContent>
            </Empty>
          ) : (
            <ul className="divide-y rounded-lg border">
              {sets.map(summary => {
                const active =
                  assistantMode === 'roleplay' && summary.published?.id === activeRevisionId
                const busy = busyId === summary.id
                return (
                  <li
                    key={summary.id}
                    className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium">{summary.name}</p>
                        {active ? (
                          <Badge>使用中</Badge>
                        ) : summary.published ? (
                          <Badge variant="secondary">已完成</Badge>
                        ) : (
                          <Badge variant="outline">草稿</Badge>
                        )}
                      </div>
                      <p className="mt-1 text-label text-muted-foreground">
                        {summary.published
                          ? '已完成最後檢查，可直接使用或繼續修改'
                          : '還沒完成最後檢查'}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => editSet(summary)}
                        disabled={busy}
                      >
                        {busy && <Spinner className="mr-1.5 h-3 w-3" />}
                        編輯
                      </Button>
                      {summary.published && !active && (
                        <Button size="sm" onClick={() => activate(summary)} disabled={busy}>
                          使用這個角色
                        </Button>
                      )}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label="更多角色操作"
                            disabled={busy}
                          >
                            <Icon icon="fa-solid fa-ellipsis" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {summary.published && (
                            <DropdownMenuItem onSelect={() => setExportTarget(summary)}>
                              <Icon icon="fa-solid fa-download" />
                              下載設定集
                            </DropdownMenuItem>
                          )}
                          {!active && (
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={() => setArchiveTarget(summary)}
                            >
                              <Icon icon="fa-solid fa-box-archive" />
                              封存
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          {!loading && sets.length >= 5 && (
            <p className="mt-3 text-label text-muted-foreground">
              已達 5 組上限；若要建立新角色，請先封存一組目前未使用的角色。
            </p>
          )}
        </CardContent>
      </Card>

      <RoleplayImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        channelId={channelId}
        existingDigests={sets.flatMap(item =>
          item.published ? [item.published.content_digest] : []
        )}
        atLimit={sets.length >= 5}
        onImported={handleImported}
        onCloseAutoFocus={() => importTriggerRef.current?.focus()}
      />

      <AlertDialog
        open={exportTarget !== null}
        onOpenChange={open => !open && setExportTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>下載「{exportTarget?.name}」的設定集？</AlertDialogTitle>
            <AlertDialogDescription>
              檔案包含完整作品範圍、角色不知道的內容與背景條目，也可能含有後續劇情。請只交給信任的人。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={exporting}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void downloadExport()} disabled={exporting}>
              {exporting && <Spinner className="mr-1.5 h-3 w-3" />}
              確認下載設定集
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={archiveTarget !== null}
        onOpenChange={open => !open && setArchiveTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>封存「{archiveTarget?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              封存後會從角色清單隱藏，但不會刪除已完成的設定。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => archiveTarget && void archive(archiveTarget)}
              disabled={archiveTarget ? busyId === archiveTarget.id : false}
            >
              確認封存
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

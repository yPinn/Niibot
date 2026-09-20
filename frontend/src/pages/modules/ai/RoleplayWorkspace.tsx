import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  activateRoleplayRevision,
  archiveRoleplaySet,
  getRoleplaySet,
  listRoleplaySets,
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
  AlertDialogTrigger,
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Skeleton,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

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
      toast.success('故事角色已封存')
    } catch (error) {
      toastApiError(error, '封存故事角色失敗')
    } finally {
      setBusyId(null)
    }
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
    <Card>
      <CardHeader>
        <div>
          <CardTitle>故事角色</CardTitle>
          <CardDescription className="mt-1">
            每個角色都連同作品範圍、故事時間點與知識界線保存；最多建立 5 組。
          </CardDescription>
        </div>
        {!loading && sets.length > 0 && (
          <CardAction>
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
                從作品範圍與人物小傳開始，約七個步驟就能建立第一個可使用的角色。
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button onClick={() => setEditing('new')}>建立故事角色</Button>
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
                      {summary.published ? '可直接使用，也能繼續調整後更新' : '尚未完成發布前檢查'}
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
                    {!active && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="sm" disabled={busy}>
                            封存
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>封存「{summary.name}」？</AlertDialogTitle>
                            <AlertDialogDescription>
                              角色會從一般清單隱藏，但已發布內容仍保留在系統中。
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>取消</AlertDialogCancel>
                            <AlertDialogAction onClick={() => archive(summary)}>
                              確認封存
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
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
  )
}

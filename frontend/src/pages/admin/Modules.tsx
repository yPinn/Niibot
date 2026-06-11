import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  type BotEmoteChannel,
  getBotEmotes,
  getModuleAIPacks,
  resyncBotEmotes,
  setModuleAIPacks,
} from '@/api/admin'
import { getAIPacks, type Pack } from '@/api/aiSettings'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, Spinner } from '@/components/primitives'
import { Button, Card, CardContent, CardHeader, CardTitle, Skeleton, Switch } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { EmoteChip } from '@/pages/modules/ai/EmoteSection'

export default function AdminModules() {
  useDocumentTitle('Admin · Modules')

  const [availablePacks, setAvailablePacks] = useState<Pack[]>([])
  const [enabledPacks, setEnabledPacks] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const [botEmotes, setBotEmotes] = useState<BotEmoteChannel[]>([])
  const [emotesLoading, setEmotesLoading] = useState(true)
  const [resyncing, setResyncing] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    Promise.all([getAIPacks(), getModuleAIPacks()])
      .then(([packs, enabled]) => {
        setAvailablePacks(packs)
        setEnabledPacks(enabled)
      })
      .catch(() => toast.error('載入失敗'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    getBotEmotes()
      .then(setBotEmotes)
      .catch(() => toast.error('貼圖狀態載入失敗'))
      .finally(() => setEmotesLoading(false))
  }, [])

  async function handleToggle(packId: string) {
    const prev = enabledPacks
    const next = prev.includes(packId) ? prev.filter(id => id !== packId) : [...prev, packId]
    setEnabledPacks(next)
    try {
      await setModuleAIPacks(next)
    } catch {
      setEnabledPacks(prev)
      toast.error('更新失敗，請重試')
    }
  }

  function toggleExpanded(channelId: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(channelId)) next.delete(channelId)
      else next.add(channelId)
      return next
    })
  }

  async function handleResync(channelId?: string) {
    setResyncing(channelId ?? 'all')
    try {
      const results = await resyncBotEmotes(channelId)
      const updated = results.filter(r => r.synced).length
      toast.success(updated > 0 ? `已更新 ${updated} 個頻道的可用貼圖` : '貼圖已是最新狀態')
      const fresh = await getBotEmotes()
      setBotEmotes(fresh)
    } catch {
      toast.error('重新同步失敗，請重試')
    } finally {
      setResyncing(null)
    }
  }

  return (
    <PageMain>
      <PageHeader
        title="Modules"
        description="全域模組設定，適用於所有頻道。知識包變更即時生效，無需重啟。"
      />

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>知識包</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-label text-muted-foreground">
            啟用的知識包供所有頻道的 AI 使用。觀眾提問命中條目關鍵字時，相關段落自動注入回答語境。
          </p>
          {loading ? (
            <div className="flex flex-col gap-2 mt-1">
              {[1, 2].map(i => (
                <Skeleton key={i} className="h-14 w-full rounded-md" />
              ))}
            </div>
          ) : availablePacks.length === 0 ? (
            <p className="text-sub text-muted-foreground py-2">尚無可用知識包。</p>
          ) : (
            <div className="flex flex-col gap-2 mt-1">
              {availablePacks.map(pack => (
                <div
                  key={pack.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2.5"
                >
                  <div className="flex flex-col gap-0.5 pr-4 min-w-0">
                    <span className="text-sub font-medium">{pack.name}</span>
                    <span className="text-label text-muted-foreground">{pack.description}</span>
                  </div>
                  <Switch
                    checked={enabledPacks.includes(pack.id)}
                    onCheckedChange={() => handleToggle(pack.id)}
                  />
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Bot 貼圖同步</CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleResync()}
              disabled={resyncing !== null || emotesLoading}
            >
              {resyncing === 'all' ? (
                <Spinner className="mr-1.5 h-3 w-3" />
              ) : (
                <Icon icon="fa-solid fa-rotate" className="mr-1.5 text-label" />
              )}
              全部重新同步
            </Button>
          </div>
          <p className="text-label text-muted-foreground">
            列出 Bot 在各頻道能使用的訂閱／追隨／小奇點貼圖（半透明表示無權限）。Bot
            帳號追隨或訂閱頻道後不會自動生效，按「重新同步」即可把最新可用清單寫入 Bot 的回覆設定。
          </p>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {emotesLoading && botEmotes.length === 0 ? (
            <div className="flex flex-col gap-2">
              {[1, 2, 3].map(i => (
                <Skeleton key={i} className="h-12 w-full rounded-md" />
              ))}
            </div>
          ) : botEmotes.length === 0 ? (
            <p className="text-sub text-muted-foreground py-2">尚無啟用中的頻道。</p>
          ) : (
            botEmotes.map(ch => {
              const isOpen = expanded.has(ch.channel_id)
              const blocked = ch.total_count - ch.available_count
              return (
                <div key={ch.channel_id} className="rounded-md border">
                  <div className="flex items-center gap-3 px-3 py-2.5">
                    <button
                      type="button"
                      onClick={() => toggleExpanded(ch.channel_id)}
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      disabled={ch.total_count === 0}
                    >
                      <Icon
                        icon={isOpen ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right'}
                        size="xs"
                        className={`shrink-0 text-muted-foreground ${ch.total_count === 0 ? 'opacity-0' : ''}`}
                      />
                      {ch.avatar ? (
                        <img
                          src={ch.avatar}
                          alt=""
                          className="h-7 w-7 shrink-0 rounded-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="h-7 w-7 shrink-0 rounded-full bg-muted" />
                      )}
                      <span className="truncate text-sub font-medium">
                        {ch.display_name || ch.name || ch.channel_id}
                      </span>
                    </button>
                    <span
                      className={`shrink-0 font-mono text-label ${blocked > 0 ? 'text-status-offline' : 'text-muted-foreground'}`}
                    >
                      可用 {ch.available_count} / {ch.total_count}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleResync(ch.channel_id)}
                      disabled={resyncing !== null}
                    >
                      {resyncing === ch.channel_id ? (
                        <Spinner className="h-3 w-3" />
                      ) : (
                        <Icon icon="fa-solid fa-rotate" className="text-label" />
                      )}
                    </Button>
                  </div>
                  {isOpen && ch.total_count > 0 && (
                    <div className="scrollbar grid max-h-72 grid-cols-[repeat(auto-fill,minmax(5rem,1fr))] gap-1 overflow-y-auto border-t p-3">
                      {ch.emotes.map(emote => (
                        <EmoteChip
                          key={emote.id}
                          emote={emote}
                          prefix=""
                          available={emote.available}
                          channelBadges={null}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )
            })
          )}
        </CardContent>
      </Card>
    </PageMain>
  )
}

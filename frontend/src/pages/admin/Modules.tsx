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
import { Icon, Spinner, TwitchRoleBadge } from '@/components/primitives'
import { Button, Card, CardContent, CardHeader, CardTitle, Skeleton, Switch } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toastApiError } from '@/lib/toast-error'
import { EmoteSection } from '@/pages/modules/ai/EmoteSection'
import { longestCommonPrefix } from '@/pages/modules/ai/utils'

export default function AdminModules() {
  useDocumentTitle('Admin · Modules')

  const [availablePacks, setAvailablePacks] = useState<Pack[]>([])
  const [enabledPacks, setEnabledPacks] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const [botEmotes, setBotEmotes] = useState<BotEmoteChannel[]>([])
  const [emotesLoading, setEmotesLoading] = useState(true)
  const [resyncing, setResyncing] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

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
      .then(data => {
        setBotEmotes(data)
        setSelectedId(prev => prev ?? data[0]?.channel_id ?? null)
      })
      .catch(() => toast.error('貼圖狀態載入失敗'))
      .finally(() => setEmotesLoading(false))
  }, [])

  async function handleToggle(packId: string) {
    const prev = enabledPacks
    const next = prev.includes(packId) ? prev.filter(id => id !== packId) : [...prev, packId]
    setEnabledPacks(next)
    try {
      await setModuleAIPacks(next)
    } catch (e) {
      setEnabledPacks(prev)
      toastApiError(e, '更新失敗，請重試')
    }
  }

  async function handleResync(channelId?: string) {
    setResyncing(channelId ?? 'all')
    try {
      const results = await resyncBotEmotes(channelId)
      const updated = results.filter(r => r.synced).length
      toast.success(updated > 0 ? `已更新 ${updated} 個頻道的可用貼圖` : '貼圖已是最新狀態')
      const fresh = await getBotEmotes()
      setBotEmotes(fresh)
    } catch (e) {
      toastApiError(e, '重新同步失敗，請重試')
    } finally {
      setResyncing(null)
    }
  }

  const selectedChannel = botEmotes.find(c => c.channel_id === selectedId) ?? null
  const selectedPrefix = selectedChannel
    ? longestCommonPrefix(selectedChannel.emotes.map(e => e.name))
    : ''

  return (
    <PageMain>
      <PageHeader
        title="Modules"
        description="全域模組設定，適用於所有頻道。知識包變更即時生效，無需重啟。"
      />

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
        <CardContent>
          {emotesLoading && botEmotes.length === 0 ? (
            <div className="flex flex-col gap-2">
              {[1, 2, 3].map(i => (
                <Skeleton key={i} className="h-12 w-full rounded-md" />
              ))}
            </div>
          ) : botEmotes.length === 0 ? (
            <p className="text-sub text-muted-foreground py-2">尚無啟用中的頻道。</p>
          ) : (
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
              {/* Left: selectable channel cards — grows to absorb leftover width */}
              <div className="grid content-start grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2 xl:flex-1">
                {botEmotes.map(ch => {
                  const blocked = ch.total_count - ch.available_count
                  const isSelected = ch.channel_id === selectedId
                  return (
                    <button
                      key={ch.channel_id}
                      type="button"
                      onClick={() => setSelectedId(ch.channel_id)}
                      className={`flex items-center gap-2.5 rounded-md border px-3 py-2.5 text-left transition-colors ${
                        isSelected ? 'border-primary bg-accent' : 'hover:bg-muted/50'
                      }`}
                    >
                      {ch.avatar ? (
                        <img
                          src={ch.avatar}
                          alt=""
                          className="h-8 w-8 shrink-0 rounded-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="h-8 w-8 shrink-0 rounded-full bg-muted" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1">
                          <span className="truncate text-sub font-medium">
                            {ch.display_name || ch.name || ch.channel_id}
                          </span>
                          {ch.is_subscribed && (
                            <TwitchRoleBadge role="subscriber" size={18} className="shrink-0" />
                          )}
                        </div>
                        <div
                          className={`font-mono text-label ${blocked > 0 ? 'text-status-offline' : 'text-muted-foreground'}`}
                        >
                          可用 {ch.available_count} / {ch.total_count}
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Right: emote panel — fixed to fit exactly 10 emotes (5rem) per row */}
              <div className="xl:sticky xl:top-4 xl:w-[56rem] xl:shrink-0">
                {selectedChannel ? (
                  <div className="rounded-md border">
                    <div className="flex items-center gap-3 border-b px-3 py-2.5">
                      {selectedChannel.avatar ? (
                        <img
                          src={selectedChannel.avatar}
                          alt=""
                          className="h-7 w-7 shrink-0 rounded-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="h-7 w-7 shrink-0 rounded-full bg-muted" />
                      )}
                      <span className="min-w-0 flex-1 truncate text-sub font-medium">
                        {selectedChannel.display_name ||
                          selectedChannel.name ||
                          selectedChannel.channel_id}
                      </span>
                      <span
                        className={`shrink-0 font-mono text-label ${
                          selectedChannel.total_count - selectedChannel.available_count > 0
                            ? 'text-status-offline'
                            : 'text-muted-foreground'
                        }`}
                      >
                        可用 {selectedChannel.available_count} / {selectedChannel.total_count}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleResync(selectedChannel.channel_id)}
                        disabled={resyncing !== null}
                      >
                        {resyncing === selectedChannel.channel_id ? (
                          <Spinner className="h-3 w-3" />
                        ) : (
                          <Icon icon="fa-solid fa-rotate" className="text-label" />
                        )}
                      </Button>
                    </div>
                    {selectedChannel.total_count > 0 ? (
                      <div className="scrollbar flex max-h-[28rem] flex-col gap-4 overflow-y-auto p-3">
                        <EmoteSection
                          label="追隨者"
                          emotes={selectedChannel.emotes.filter(e => e.emote_type === 'follower')}
                          prefix={selectedPrefix}
                          channelBadges={null}
                        />
                        <EmoteSection
                          label="訂閱者"
                          emotes={selectedChannel.emotes.filter(
                            e => e.emote_type === 'subscriptions'
                          )}
                          prefix={selectedPrefix}
                          channelBadges={null}
                        />
                        <EmoteSection
                          label="Bits"
                          emotes={selectedChannel.emotes.filter(e => e.emote_type === 'bitstier')}
                          prefix={selectedPrefix}
                          channelBadges={null}
                        />
                        <EmoteSection
                          label="其他"
                          emotes={selectedChannel.emotes.filter(
                            e => !['follower', 'subscriptions', 'bitstier'].includes(e.emote_type)
                          )}
                          prefix={selectedPrefix}
                          channelBadges={null}
                        />
                      </div>
                    ) : (
                      <p className="px-3 py-6 text-center text-sub text-muted-foreground">
                        此頻道沒有頻道貼圖。
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex h-40 items-center justify-center rounded-md border border-dashed text-sub text-muted-foreground">
                    選擇一個頻道查看貼圖
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

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
    </PageMain>
  )
}

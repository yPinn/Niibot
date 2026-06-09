import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { getModuleAIPacks, setModuleAIPacks } from '@/api/admin'
import { getAIPacks, type Pack } from '@/api/aiSettings'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import { Card, CardContent, CardHeader, CardTitle, Skeleton, Switch } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function AdminModules() {
  useDocumentTitle('Admin · Modules')

  const [availablePacks, setAvailablePacks] = useState<Pack[]>([])
  const [enabledPacks, setEnabledPacks] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getAIPacks(), getModuleAIPacks()])
      .then(([packs, enabled]) => {
        setAvailablePacks(packs)
        setEnabledPacks(enabled)
      })
      .catch(() => toast.error('載入失敗'))
      .finally(() => setLoading(false))
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
    </PageMain>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  type CheckinCollectionCatalog,
  getCheckinCollections,
  updateCheckinCollection,
} from '@/api/checkin'
import { Icon, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

const ALL_SETS = '__all__'

const PREVIEW_CATALOG: CheckinCollectionCatalog = {
  selected_set_key: null,
  total_cards: 1,
  sets: [
    {
      key: 'aespa',
      name: 'aespa',
      card_count: 1,
      cards: [
        {
          key: 'karina-01',
          number: 1,
          name: 'Karina',
          portrait_url: '/images/collections/aespa/karina-01-r1.webp',
          rarity_key: 'common',
          rarity_name: '普通',
        },
      ],
    },
  ],
}

interface CheckinCollectionSettingsProps {
  preview?: boolean
}

export function CheckinCollectionSettings({ preview = false }: CheckinCollectionSettingsProps) {
  const [catalog, setCatalog] = useState<CheckinCollectionCatalog | null>(
    preview ? PREVIEW_CATALOG : null
  )
  const [loading, setLoading] = useState(!preview)
  const [loadFailed, setLoadFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState(ALL_SETS)
  const saveLocked = useRef(false)

  const load = async () => {
    if (preview) return
    setLoading(true)
    setLoadFailed(false)
    try {
      setCatalog(await getCheckinCollections())
    } catch (error) {
      setLoadFailed(true)
      toastApiError(error, '卡片圖鑑載入失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (preview) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
    // The retry action uses the same tenant-scoped loader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview])

  const visibleSets = useMemo(
    () => catalog?.sets.filter(item => filter === ALL_SETS || item.key === filter) ?? [],
    [catalog, filter]
  )

  const handleSelection = async (value: string) => {
    if (!catalog || saveLocked.current) return
    const nextSetKey = value === ALL_SETS ? null : value
    if (nextSetKey === catalog.selected_set_key) return

    const previous = catalog
    saveLocked.current = true
    setSaving(true)
    setCatalog({ ...catalog, selected_set_key: nextSetKey })
    try {
      const next = preview
        ? { ...catalog, selected_set_key: nextSetKey }
        : await updateCheckinCollection(nextSetKey)
      setCatalog(next)
      toast.success('抽卡範圍已更新')
    } catch (error) {
      setCatalog(previous)
      toastApiError(error, '更新抽卡範圍失敗')
    } finally {
      saveLocked.current = false
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div aria-label="載入卡片設定" className="grid gap-element sm:grid-cols-[minmax(0,1fr)_auto]">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-32" />
      </div>
    )
  }

  if (loadFailed || !catalog) {
    return (
      <Alert variant="destructive">
        <Icon icon="fa-solid fa-circle-exclamation" />
        <AlertTitle>卡片圖鑑載入失敗</AlertTitle>
        <AlertDescription>
          <Button
            size="sm"
            variant="outline"
            aria-label="重新載入卡片圖鑑"
            onClick={() => void load()}
          >
            重新載入
          </Button>
        </AlertDescription>
      </Alert>
    )
  }

  if (catalog.sets.length === 0) {
    return (
      <Alert>
        <Icon icon="fa-solid fa-layer-group" />
        <AlertTitle>目前沒有可用卡片</AlertTitle>
        <AlertDescription>發布卡片後，這裡會顯示可選擇的抽卡範圍。</AlertDescription>
      </Alert>
    )
  }

  const selectedValue = catalog.selected_set_key ?? ALL_SETS

  return (
    <section aria-labelledby="checkin-collection-title" className="border-t pt-section">
      <div className="flex flex-col gap-element sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h4 id="checkin-collection-title" className="text-sub font-medium">
            抽卡範圍
          </h4>
          <p className="text-label text-muted-foreground">
            {catalog.total_cards} 張 · {catalog.sets.length} 個卡組
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-element">
          <Select
            value={selectedValue}
            disabled={saving}
            onValueChange={value => void handleSelection(value)}
          >
            <SelectTrigger size="sm" aria-label="抽卡範圍" className="min-w-40">
              {saving ? <Spinner /> : null}
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper" align="end">
              <SelectItem value={ALL_SETS}>全部卡組（{catalog.total_cards} 張）</SelectItem>
              {catalog.sets.map(item => (
                <SelectItem key={item.key} value={item.key}>
                  {item.name}（{item.card_count} 張）
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Dialog onOpenChange={open => open && setFilter(ALL_SETS)}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">
                <Icon icon="fa-solid fa-table-cells" />
                查看卡片圖鑑
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[min(88vh,56rem)] grid-rows-[auto_auto_minmax(0,1fr)] sm:max-w-5xl">
              <DialogHeader>
                <DialogTitle>卡片圖鑑</DialogTitle>
                <DialogDescription>檢查目前發布的 2:3 卡面與卡片資料。</DialogDescription>
              </DialogHeader>

              <div aria-label="圖鑑篩選" className="flex flex-wrap gap-2 pr-8">
                <Button
                  size="sm"
                  variant={filter === ALL_SETS ? 'default' : 'outline'}
                  aria-pressed={filter === ALL_SETS}
                  onClick={() => setFilter(ALL_SETS)}
                >
                  全部 {catalog.total_cards}
                </Button>
                {catalog.sets.map(item => (
                  <Button
                    key={item.key}
                    size="sm"
                    variant={filter === item.key ? 'default' : 'outline'}
                    aria-pressed={filter === item.key}
                    onClick={() => setFilter(item.key)}
                  >
                    {item.name} {item.card_count}
                  </Button>
                ))}
              </div>

              <div className="min-h-0 overflow-y-auto overscroll-contain pr-1">
                <div className="grid grid-cols-2 gap-element sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
                  {visibleSets.flatMap(set =>
                    set.cards.map(card => {
                      const cardNumber = String(card.number).padStart(3, '0')
                      return (
                        <figure
                          key={`${set.key}:${card.key}`}
                          className="min-w-0 overflow-hidden rounded-lg bg-muted"
                        >
                          <img
                            src={card.portrait_url}
                            alt={`${set.name} #${cardNumber} ${card.name}`}
                            loading="lazy"
                            decoding="async"
                            className="aspect-[2/3] w-full bg-background object-cover"
                          />
                          <figcaption className="space-y-1 p-element">
                            <div className="flex items-center justify-between gap-1">
                              <span className="truncate text-label font-medium">{card.name}</span>
                              <Badge variant="outline" className="shrink-0 text-[0.625rem]">
                                {card.rarity_name}
                              </Badge>
                            </div>
                            <p className="truncate text-[0.6875rem] tabular-nums text-muted-foreground">
                              {set.name} · #{cardNumber}
                            </p>
                          </figcaption>
                        </figure>
                      )
                    })
                  )}
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </section>
  )
}

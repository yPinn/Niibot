import { useState } from 'react'
import { toast } from 'sonner'

import {
  type CheckinClearScope,
  type CheckinDataSummary,
  clearCheckinData,
  exportCheckinData,
  getCheckinDataSummary,
} from '@/api/checkin'
import { Spinner } from '@/components/primitives'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  Button,
  Input,
  Label,
  Skeleton,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

interface CheckinDataManagementProps {
  onDataChanged: () => void | Promise<void>
}

export function CheckinDataManagement({ onDataChanged }: CheckinDataManagementProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [summary, setSummary] = useState<CheckinDataSummary | null>(null)
  const [scope, setScope] = useState<CheckinClearScope>('imported')
  const [confirmation, setConfirmation] = useState('')
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [exporting, setExporting] = useState(false)

  const loadSummary = async () => {
    setLoadingSummary(true)
    try {
      setSummary(await getCheckinDataSummary())
    } catch (error) {
      setSummary(null)
      toastApiError(error, '載入簽到資料摘要失敗')
    } finally {
      setLoadingSummary(false)
    }
  }

  const handleDialogOpenChange = (nextOpen: boolean) => {
    setDialogOpen(nextOpen)
    if (nextOpen) {
      setScope('imported')
      setConfirmation('')
      void loadSummary()
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const download = await exportCheckinData()
      const url = URL.createObjectURL(download.blob)
      const link = document.createElement('a')
      try {
        link.href = url
        link.download = download.filename
        document.body.append(link)
        link.click()
        link.remove()
      } finally {
        URL.revokeObjectURL(url)
      }
      toast.success('簽到 CSV 已匯出')
    } catch (error) {
      toastApiError(error, '匯出簽到資料失敗')
    } finally {
      setExporting(false)
    }
  }

  const scopeHasData =
    summary !== null &&
    (scope === 'imported'
      ? summary.imported_viewers > 0
      : summary.ledger_checkins +
          summary.imported_days +
          summary.card_draws +
          summary.checkin_events >
        0)
  const confirmationMatches =
    summary !== null &&
    confirmation.trim().toLocaleLowerCase() === summary.confirmation_text.toLocaleLowerCase()

  const handleClear = async () => {
    if (!summary || !scopeHasData || !confirmationMatches) return
    setClearing(true)
    try {
      await clearCheckinData(scope, confirmation.trim())
      await onDataChanged()
      setDialogOpen(false)
      toast.success(scope === 'imported' ? '轉移資料已撤銷' : '簽到資料已清除')
    } catch (error) {
      toastApiError(error, '清除簽到資料失敗')
    } finally {
      setClearing(false)
    }
  }

  return (
    <section className="space-y-3 border-t pt-card" aria-labelledby="checkin-data-title">
      <div className="space-y-1">
        <h3 id="checkin-data-title" className="text-card-title font-semibold">
          資料管理
        </h3>
        <p className="text-sub text-muted-foreground">
          匯出可再次匯入的簽到摘要；不包含逐日歷史、收藏卡與畫面事件。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => void handleExport()}
          disabled={exporting}
        >
          {exporting && <Spinner />}
          匯出 CSV
        </Button>
        <AlertDialog open={dialogOpen} onOpenChange={handleDialogOpenChange}>
          <AlertDialogTrigger asChild>
            <Button type="button" variant="outline">
              清除簽到資料
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>清除簽到資料</AlertDialogTitle>
              <AlertDialogDescription>
                選擇資料範圍並輸入頻道名稱。簽到時區、訊息模板與獎勵綁定都會保留。
              </AlertDialogDescription>
            </AlertDialogHeader>

            {loadingSummary ? (
              <div className="space-y-3" aria-label="載入資料影響">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-9 w-full" />
              </div>
            ) : summary ? (
              <div className="space-y-card">
                <fieldset className="space-y-3">
                  <legend className="text-sm font-medium">要清除哪些資料？</legend>
                  <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3 has-[:checked]:border-primary has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring">
                    <input
                      type="radio"
                      name="checkin-clear-scope"
                      value="imported"
                      checked={scope === 'imported'}
                      onChange={() => setScope('imported')}
                      className="mt-1 accent-primary"
                    />
                    <span className="space-y-1">
                      <span className="block text-sm font-medium">只撤銷轉移資料（建議）</span>
                      <span className="block text-label text-muted-foreground">
                        保留在 Niibot 產生的簽到與收藏，只移除先前承接的資料。
                      </span>
                    </span>
                  </label>
                  <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3 has-[:checked]:border-destructive has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring">
                    <input
                      type="radio"
                      name="checkin-clear-scope"
                      value="all"
                      checked={scope === 'all'}
                      onChange={() => setScope('all')}
                      className="mt-1 accent-primary"
                    />
                    <span className="space-y-1">
                      <span className="block text-sm font-medium">清除全部簽到與收藏</span>
                      <span className="block text-label text-muted-foreground">
                        包含轉移資料、Niibot 簽到、收藏卡與簽到畫面事件。
                      </span>
                    </span>
                  </label>
                </fieldset>

                <p
                  className={
                    scope === 'all'
                      ? 'text-sm font-medium text-destructive'
                      : 'text-sm text-muted-foreground'
                  }
                  role="status"
                >
                  {scope === 'imported'
                    ? summary.imported_viewers > 0
                      ? `將撤銷 ${summary.imported_viewers} 位觀眾、${summary.imported_days} 天轉移資料。`
                      : '目前沒有可撤銷的轉移資料。'
                    : `將永久清除 ${summary.total_days} 天累積資料，其中有 ${summary.ledger_checkins} 筆簽到與 ${summary.card_draws} 張收藏卡。`}
                </p>

                <div className="space-y-2">
                  <Label htmlFor="checkin-clear-confirmation">輸入頻道名稱以確認</Label>
                  <Input
                    id="checkin-clear-confirmation"
                    value={confirmation}
                    autoComplete="off"
                    placeholder={summary.confirmation_text}
                    onChange={event => setConfirmation(event.target.value)}
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-2" role="alert">
                <p className="text-sm text-destructive">無法載入清除範圍，尚未變更任何資料。</p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void loadSummary()}
                >
                  重新載入
                </Button>
              </div>
            )}

            <AlertDialogFooter>
              <AlertDialogCancel disabled={clearing}>取消</AlertDialogCancel>
              <Button
                type="button"
                variant="destructive"
                disabled={clearing || loadingSummary || !scopeHasData || !confirmationMatches}
                onClick={() => void handleClear()}
              >
                {clearing && <Spinner />}
                確認清除
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </section>
  )
}

import { useCallback, useEffect, useState } from 'react'

import { getPendingActivationCodes, type PendingCode } from '@/api/admin'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Icon,
  Separator,
  Skeleton,
  SlideUp,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function AdminActivationCodes() {
  useDocumentTitle('啟用碼')
  const [codes, setCodes] = useState<PendingCode[]>([])
  const [loading, setLoading] = useState(true)
  // Snapshot of "now" taken when data loads — avoids calling Date.now() during render
  const [nowMs, setNowMs] = useState(0)

  const fetchCodes = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getPendingActivationCodes()
      setCodes(data)
      setNowMs(Date.now())
    } catch {
      setCodes([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    getPendingActivationCodes()
      .then(data => {
        setCodes(data)
        setNowMs(Date.now())
      })
      .catch(() => setCodes([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <PageMain className="lg:gap-card">
      <PageHeader
        title="Activation Codes"
        description="透過忠誠點數兌換產生、尚未使用的 OTP 代碼。"
      />

      <SlideUp>
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Icon icon="fa-solid fa-key" size="sm" wrapperClassName="text-muted-foreground" />
              <CardTitle className="text-card-title">待使用啟用碼</CardTitle>
            </div>
            <CardAction>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-label">
                  {loading ? '…' : codes.length}
                </Badge>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => {
                    setLoading(true)
                    void fetchCodes()
                  }}
                  aria-label="Refresh"
                >
                  <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
                </Button>
              </div>
            </CardAction>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : codes.length === 0 ? (
              <p className="text-sub text-muted-foreground py-2">目前沒有待使用的啟用碼。</p>
            ) : (
              codes.map((code, idx) => {
                const label = code.display_name ?? code.username ?? code.platform_user_id
                const hoursLeft = Math.max(
                  0,
                  Math.round((new Date(code.expires_at).getTime() - nowMs) / 3_600_000)
                )
                const isExpiringSoon = hoursLeft <= 12
                return (
                  <div key={code.platform_user_id + code.expires_at}>
                    {idx > 0 && <Separator className="opacity-40" />}
                    <div className="flex items-center gap-3 py-2">
                      {code.avatar ? (
                        <img
                          src={code.avatar}
                          alt={label}
                          className="size-7 rounded-full shrink-0 object-cover"
                        />
                      ) : (
                        <div className="size-7 rounded-full bg-muted shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sub font-medium truncate">{label}</p>
                        <p className="text-label text-muted-foreground font-mono truncate">
                          {code.platform_user_id}
                        </p>
                      </div>
                      <Badge
                        variant="outline"
                        className={`font-mono text-label shrink-0 ${
                          isExpiringSoon ? 'border-status-offline/30 text-status-offline' : ''
                        }`}
                      >
                        {hoursLeft}h 後過期
                      </Badge>
                    </div>
                  </div>
                )
              })
            )}
          </CardContent>
        </Card>
      </SlideUp>
    </PageMain>
  )
}

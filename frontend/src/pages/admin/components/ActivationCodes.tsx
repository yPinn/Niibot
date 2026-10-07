import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  createOwnerCode,
  getGrants,
  getOnboardingFunnel,
  type Grant,
  type OnboardingFunnel,
  revokeGrant,
} from '@/api/admin'
import { Icon, Spinner } from '@/components/primitives'
import {
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
} from '@/components/ui'
import { formatDateTimeShort } from '@/lib/format'
import { toastApiError } from '@/lib/toast-error'

/** Outstanding activation codes. Channel-point redemptions issue most codes
 * automatically, so the admin only needs what's still actionable: unused
 * codes (to revoke) plus a one-line 30-day funnel. */
export function ActivationCodes() {
  const [funnel, setFunnel] = useState<OnboardingFunnel | null>(null)
  const [codes, setCodes] = useState<Grant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [revoking, setRevoking] = useState<number | null>(null)
  const [issuing, setIssuing] = useState(false)

  // The summary is an aside; a failed load just hides it.
  const fetchFunnel = useCallback(async () => {
    try {
      setFunnel(await getOnboardingFunnel())
    } catch {
      setFunnel(null)
    }
  }, [])

  const fetchCodes = useCallback(async () => {
    setError(false)
    try {
      setCodes(await getGrants({ status: 'issued' }))
    } catch {
      setCodes([])
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    void fetchFunnel()
    void fetchCodes()
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [fetchFunnel, fetchCodes])

  const retry = () => {
    setLoading(true)
    void fetchCodes()
  }

  const handleIssue = async () => {
    setIssuing(true)
    try {
      const code = await createOwnerCode()
      toast.success(`啟用碼：${code}`, { description: '72 小時內有效，單次使用', duration: 15000 })
      void fetchCodes()
      void fetchFunnel()
    } catch (e) {
      toastApiError(e, '產生啟用碼失敗')
    } finally {
      setIssuing(false)
    }
  }

  const handleRevoke = async (id: number) => {
    setRevoking(id)
    try {
      await revokeGrant(id)
      setCodes(prev => prev.filter(g => g.id !== id))
      void fetchFunnel()
    } catch (e) {
      toastApiError(e, '撤銷失敗')
    } finally {
      setRevoking(null)
    }
  }

  const cp = funnel?.by_kind.find(k => k.kind === 'channel_points')
  const summary =
    cp && cp.issued_30d > 0
      ? `近 30 日 發出 ${cp.issued_30d} · 啟用 ${cp.consumed_30d}（${Math.round((cp.consumed_30d / cp.issued_30d) * 100)}%）`
      : null

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon="fa-solid fa-key" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle className="text-card-title">啟用碼</CardTitle>
        </div>
        {summary && (
          <CardDescription className="text-label tabular-nums">{summary}</CardDescription>
        )}
        <CardAction>
          <Button size="sm" variant="outline" onClick={handleIssue} disabled={issuing}>
            {issuing ? <Spinner /> : <Icon icon="fa-solid fa-plus" size="xs" />}
            產生
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-10 w-full rounded-lg" />
        ) : error ? (
          <div role="alert" className="flex items-center justify-between gap-element">
            <p className="text-label text-destructive">載入失敗</p>
            <Button variant="ghost" size="sm" onClick={retry}>
              重試
            </Button>
          </div>
        ) : codes.length === 0 ? (
          <p className="text-label text-muted-foreground">沒有待使用的啟用碼</p>
        ) : (
          <ul className="divide-y overflow-hidden rounded-lg border">
            {codes.map(g => {
              const label = g.display_name ?? g.username ?? g.platform_user_id ?? '尚未綁定'
              return (
                <li
                  key={g.id}
                  aria-label={`${label} 的啟用碼`}
                  className="flex items-center gap-element px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sub font-medium">{label}</p>
                    <p className="truncate text-label tabular-nums text-muted-foreground">
                      <span className="font-mono font-semibold tracking-wider text-foreground">
                        {g.code_plain ?? '—'}
                      </span>
                      {` · ${formatDateTimeShort(g.expires_at)} 到期`}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={revoking === g.id}
                    onClick={() => handleRevoke(g.id)}
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label={`撤銷 ${label} 的啟用碼`}
                  >
                    {revoking === g.id ? <Spinner /> : '撤銷'}
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

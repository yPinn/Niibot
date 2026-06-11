import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, Stagger, StaggerItem } from '@/components/primitives'
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui'
import { WipLockOverlay } from '@/components/WipLockOverlay'
import { SHOW_WIP_LOCK } from '@/config/env'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const ECPAY_URL: string | undefined = import.meta.env.VITE_SUPPORT_ECPAY_URL

const PERKS = [
  { icon: 'fa-solid fa-server', text: '伺服器基礎設施與主機費用' },
  { icon: 'fa-solid fa-code', text: '持續功能開發' },
  { icon: 'fa-solid fa-bug', text: 'Bug 修復與穩定性改善' },
  { icon: 'fa-solid fa-headset', text: '社群支援與日常維護' },
] as const

export default function Support() {
  useDocumentTitle('Support')

  return (
    <PageMain>
      <PageHeader title="Support Development" description="Help keep Niibot alive and growing." />

      <Stagger className="flex flex-col items-center gap-section">
        <StaggerItem className="w-full max-w-md">
          <Card>
            <CardHeader className="items-center text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <Icon icon="fa-solid fa-mug-hot" size="xl" className="text-primary" />
              </div>
              <CardTitle>贊助開發者</CardTitle>
              <CardDescription>
                Niibot 是在業餘時間維護的開源專案。你的支持能幫助支付伺服器費用，並持續開發新功能。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col items-center gap-section">
              {ECPAY_URL ? (
                <Button asChild size="lg" className="w-full">
                  <a href={ECPAY_URL} target="_blank" rel="noopener noreferrer">
                    <Icon icon="fa-solid fa-credit-card" size="sm" />
                    透過綠界 ECPay 贊助
                  </a>
                </Button>
              ) : (
                <p className="text-sub text-muted-foreground">贊助連結尚未設定</p>
              )}
              <p className="text-label text-center text-muted-foreground">
                付款由綠界科技 ECPay 處理，支援信用卡、ATM 及超商代碼。
              </p>
            </CardContent>
          </Card>
        </StaggerItem>

        <StaggerItem className="w-full max-w-md">
          <Card>
            <CardHeader>
              <CardTitle>你的支持用於</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {PERKS.map(({ icon, text }) => (
                  <li key={text} className="flex items-center gap-3">
                    <Icon icon={icon} size="md" className="text-primary" />
                    <span className="text-sub text-muted-foreground">{text}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </StaggerItem>
      </Stagger>
      {SHOW_WIP_LOCK && <WipLockOverlay />}
    </PageMain>
  )
}

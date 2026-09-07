import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { SlideUp } from '@/components/primitives'
import { BotAccountsCard } from '@/components/settings/BotAccountsCard'
import { PaymentConfigCard } from '@/components/settings/PaymentConfigCard'
import { WipLockOverlay } from '@/components/WipLockOverlay'
import { SHOW_WIP_LOCK } from '@/config/env'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function Settings() {
  useDocumentTitle('Settings')

  return (
    <PageMain>
      <PageHeader title="Settings" description="帳號、金流與系統設定" />

      <SlideUp inView>
        <BotAccountsCard />
      </SlideUp>

      <PaymentConfigCard />

      {SHOW_WIP_LOCK && <WipLockOverlay />}
    </PageMain>
  )
}

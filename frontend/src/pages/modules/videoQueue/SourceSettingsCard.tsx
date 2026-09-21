import { SettingRow } from '@/components/SettingRow'
import {
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Switch,
} from '@/components/ui'

import type { RulesDraft } from './RulesCard'
import { REDEMPTION_DURATION_OPTIONS } from './utils'

const GRID = 'grid grid-cols-1 gap-x-card gap-y-card sm:grid-cols-2'
const CONTROL_WIDTH = 'w-36'

export function SourceSettingsPanel({
  draft,
  onField,
  redemptionEnabled,
  onToggleRedemption,
}: {
  draft: Pick<RulesDraft, 'maxRedemptionDuration'>
  onField: (key: keyof RulesDraft, value: string) => void
  redemptionEnabled: boolean
  onToggleRedemption: (value: boolean) => void
}) {
  return (
    <div className="flex flex-col gap-card">
      <section className="flex flex-col gap-card" aria-labelledby="channel-points-source">
        <div>
          <h3 id="channel-points-source" className="text-sub font-medium">
            頻道點數
          </h3>
          <p className="text-label text-muted-foreground">Twitch 兌換專屬設定</p>
        </div>
        <div className={GRID}>
          <SettingRow
            title="開放頻道點數點播"
            description="觀眾可用已綁定的 Twitch 自訂獎勵加入影片"
          >
            <Switch checked={redemptionEnabled} onCheckedChange={onToggleRedemption} />
          </SettingRow>
          <SettingRow
            title="單次兌換長度上限"
            description="會與通用影片長度一起套用，以較短的上限為準"
          >
            <Select
              value={draft.maxRedemptionDuration}
              onValueChange={value => onField('maxRedemptionDuration', value)}
            >
              <SelectTrigger className={CONTROL_WIDTH} disabled={!redemptionEnabled}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REDEMPTION_DURATION_OPTIONS.map(option => (
                  <SelectItem key={option.value} value={String(option.value)}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingRow>
        </div>
      </section>

      <Separator />

      <section className="flex flex-col gap-card" aria-labelledby="donate-source">
        <div>
          <h3 id="donate-source" className="text-sub font-medium">
            Donate
          </h3>
          <p className="text-label text-muted-foreground">付費點播來源設定</p>
        </div>
        <SettingRow
          title="斗內影片點播"
          description="在金流設定中逐一開啟平台的影片分享；仍會套用通用安全、容量與封鎖規則"
        >
          <Button asChild variant="outline" size="sm">
            <a href="/settings">前往 Donate 設定</a>
          </Button>
        </SettingRow>
      </section>
    </div>
  )
}

import { Icon, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Switch,
} from '@/components/ui'

import { clampValue, MIN_VIEW_COUNT_OPTIONS, REDEMPTION_DURATION_OPTIONS } from './utils'

export interface RulesDraft {
  maxDurationMinutes: string
  minViewCount: string
  replayCooldownHours: string
  maxPerUser: string
  userCooldownSeconds: string
  maxQueueSize: string
  maxRedemptionDuration: string
}

const GROUP_LABEL = 'text-sub font-medium'
// A trailing lone item in an odd-sized group spans both columns instead of
// dangling in an otherwise-empty second half of the last row.
const GRID =
  'grid grid-cols-1 gap-x-card gap-y-card sm:grid-cols-2 sm:[&>*:last-child:nth-child(odd)]:col-span-2'

// Every right-side control occupies the same fixed width so the input boxes and
// the select triggers line up vertically down the card, whatever the unit.
const CONTROL_WIDTH = 'w-36'

function NumberField({
  value,
  onChange,
  min,
  max,
  placeholder,
  unit,
}: {
  value: string
  onChange: (v: string) => void
  min: number
  max: number
  placeholder: string
  unit: string
}) {
  return (
    <div className={`flex ${CONTROL_WIDTH} shrink-0 items-center justify-end gap-1.5`}>
      <Input
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        onBlur={e => onChange(clampValue(e.target.value, min, max))}
        className="w-16 text-right"
      />
      <span className="w-10 shrink-0 text-sub text-muted-foreground">{unit}</span>
    </div>
  )
}

export function RulesCard({
  draft,
  onField,
  redemptionEnabled,
  onToggleRedemption,
  onSave,
  saving,
}: {
  draft: RulesDraft
  onField: (key: keyof RulesDraft, value: string) => void
  redemptionEnabled: boolean
  onToggleRedemption: (value: boolean) => void
  onSave: () => void
  saving: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>點播規則</CardTitle>
        <CardDescription>決定觀眾可以點什麼、可以點多少</CardDescription>
        <CardAction>
          <Button size="sm" onClick={onSave} disabled={saving}>
            {saving ? (
              <Spinner className="mr-1.5" />
            ) : (
              <Icon icon="fa-solid fa-check" wrapperClassName="mr-1.5 size-3" />
            )}
            儲存變更
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-card">
        <p className={GROUP_LABEL}>觀眾可以點什麼</p>
        <div className={GRID}>
          <SettingRow title="影片最長" description="超過長度就不接受，0 代表不限">
            <NumberField
              value={draft.maxDurationMinutes}
              onChange={v => onField('maxDurationMinutes', v)}
              min={0}
              max={1440}
              placeholder="0"
              unit="分"
            />
          </SettingRow>
          <SettingRow title="至少要有多少觀看數" description="過濾冷門或惡搞的影片">
            <Select value={draft.minViewCount} onValueChange={v => onField('minViewCount', v)}>
              <SelectTrigger className={CONTROL_WIDTH}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MIN_VIEW_COUNT_OPTIONS.map(opt => (
                  <SelectItem key={opt.value} value={String(opt.value)}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingRow>
          <SettingRow title="播過多久內不能再點" description="避免同一部影片一直被重播，0 代表不限">
            <NumberField
              value={draft.replayCooldownHours}
              onChange={v => onField('replayCooldownHours', v)}
              min={0}
              max={168}
              placeholder="0"
              unit="小時"
            />
          </SettingRow>
        </div>

        <Separator />

        <p className={GROUP_LABEL}>每個人可以點多少</p>
        <div className={GRID}>
          <SettingRow title="每人同時最多" description="還在排隊的數量，0 代表不限">
            <NumberField
              value={draft.maxPerUser}
              onChange={v => onField('maxPerUser', v)}
              min={0}
              max={20}
              placeholder="0"
              unit="首"
            />
          </SettingRow>
          <SettingRow title="兩次點播間隔" description="同一個人點完，要等多久才能再點">
            <NumberField
              value={draft.userCooldownSeconds}
              onChange={v => onField('userCooldownSeconds', v)}
              min={0}
              max={3600}
              placeholder="0"
              unit="秒"
            />
          </SettingRow>
          <SettingRow title="佇列最多" description="佇列塞滿後就不再接受新的點播">
            <NumberField
              value={draft.maxQueueSize}
              onChange={v => onField('maxQueueSize', v)}
              min={1}
              max={100}
              placeholder="20"
              unit="首"
            />
          </SettingRow>
        </div>

        <Separator />

        <p className={GROUP_LABEL}>用頻道點數兌換</p>
        <div className={GRID}>
          <SettingRow
            title="開放用頻道點數兌換"
            description="觀眾可以用 Twitch 忠誠點數兌換點播（開關即時生效）"
          >
            <Switch checked={redemptionEnabled} onCheckedChange={onToggleRedemption} />
          </SettingRow>
          <SettingRow
            title="兌換時的影片長度上限"
            description="兌換點播另外算，不受上面「影片最長」影響"
          >
            <Select
              value={draft.maxRedemptionDuration}
              onValueChange={v => onField('maxRedemptionDuration', v)}
            >
              <SelectTrigger className={CONTROL_WIDTH} disabled={!redemptionEnabled}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REDEMPTION_DURATION_OPTIONS.map(opt => (
                  <SelectItem key={opt.value} value={String(opt.value)}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingRow>
        </div>
      </CardContent>
    </Card>
  )
}

import { Icon, Spinner } from '@/components/primitives'
import {
  Button,
  Card,
  CARD_HEADER_STACK_ON_MOBILE,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui'

import { type RulesDraft, RulesPanel } from './RulesCard'
import { SourceSettingsPanel } from './SourceSettingsCard'

export function SettingsCard({
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
    <Card className="h-full">
      <CardHeader className={CARD_HEADER_STACK_ON_MOBILE}>
        <div>
          <CardTitle>點播設定</CardTitle>
          <CardDescription>依加入來源與共用限制分頁管理</CardDescription>
        </div>
        <CardAction>
          <Button size="sm" onClick={onSave} disabled={saving}>
            {saving ? (
              <Spinner className="mr-1.5" />
            ) : (
              <Icon icon="fa-solid fa-check" wrapperClassName="mr-1.5 size-3" />
            )}
            儲存設定
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="sources">
          <TabsList aria-label="點播設定類型">
            <TabsTrigger value="sources">加入來源</TabsTrigger>
            <TabsTrigger value="rules">通用規則</TabsTrigger>
          </TabsList>
          <TabsContent value="sources" className="pt-element">
            <SourceSettingsPanel
              draft={draft}
              onField={onField}
              redemptionEnabled={redemptionEnabled}
              onToggleRedemption={onToggleRedemption}
            />
          </TabsContent>
          <TabsContent value="rules" className="pt-element">
            <RulesPanel draft={draft} onField={onField} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

import { Link } from 'react-router-dom'

import type { TwitchCapabilitySnapshot } from '@/api/botAccounts'
import type { CommandConfig } from '@/api/commands'
import { Alert, AlertDescription, AlertTitle, Button } from '@/components/ui'

interface CommandSetupNoticeProps {
  commands: CommandConfig[]
  snapshot: TwitchCapabilitySnapshot | null
  botModerator: boolean | null
}

function needsCommandSetup(
  commands: CommandConfig[],
  snapshot: TwitchCapabilitySnapshot | null,
  botModerator: boolean | null
): boolean {
  const enabledCommands = commands.filter(command => command.enabled)
  if (enabledCommands.length === 0) return false

  const requiredKeys = new Set(
    enabledCommands.flatMap(command =>
      command.capability_requirements.map(requirement => requirement.capability_key)
    )
  )
  const hasUnavailableCapability =
    snapshot?.capabilities.some(
      item => !item.available && (item.core || requiredKeys.has(item.key))
    ) ?? false
  const needsBotModerator = enabledCommands.some(command =>
    command.capability_requirements.some(requirement => requirement.requires_bot_moderator)
  )

  return hasUnavailableCapability || (needsBotModerator && botModerator === false)
}

export function CommandSetupNotice({ commands, snapshot, botModerator }: CommandSetupNoticeProps) {
  if (!needsCommandSetup(commands, snapshot, botModerator)) return null

  return (
    <Alert>
      <AlertTitle>部分指令功能尚未就緒</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>完成設定後即可使用完整功能，現有指令設定不會改變。</span>
        <Button asChild size="sm" variant="outline">
          <Link to="/settings">檢查設定</Link>
        </Button>
      </AlertDescription>
    </Alert>
  )
}

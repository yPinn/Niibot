import type { CommandConfig } from '@/api/commands'
import type { TriggerConfig } from '@/api/triggers'

export type SortKey = 'command_name' | 'cooldown' | 'min_role' | 'usage_count' | 'enabled'
export type CustomSortKey = 'name' | 'kind' | 'cooldown' | 'min_role' | 'usage_count'

export type EditingState =
  | { mode: 'create' }
  | { mode: 'edit-command'; command: CommandConfig }
  | { mode: 'edit-trigger'; trigger: TriggerConfig }

export type CustomRow =
  | { kind: 'command'; data: CommandConfig }
  | { kind: 'trigger'; data: TriggerConfig }

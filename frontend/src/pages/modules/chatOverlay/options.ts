import {
  type AlignOption,
  type AnimDirOption,
  type BadgeFilterOption,
  type MsgBgOption,
  type SpacingOption,
} from '../chatOverlayCss'

// Aligned to index.css semantic type scale: xs/sm/base/lg/xl/2xl
export const FONT_SIZE_STEPS: { value: number; label: string }[] = [
  { value: 12, label: 'xs' },
  { value: 14, label: 'sm' },
  { value: 16, label: 'base' },
  { value: 18, label: 'lg' },
  { value: 20, label: 'xl' },
  { value: 24, label: '2xl' },
]

export const SPACING_STEPS: { value: SpacingOption; label: string }[] = [
  { value: 'compact', label: '緊湊' },
  { value: 'normal', label: '標準' },
  { value: 'loose', label: '寬鬆' },
]

export const MSG_BG_OPTIONS: { value: MsgBgOption; label: string }[] = [
  { value: 'bubble', label: '氣泡' },
  { value: 'rounded', label: '深色圓框' },
  { value: 'dark', label: '深色方框' },
  { value: 'none', label: '無' },
]

export const ALIGN_OPTIONS: { value: AlignOption; label: string }[] = [
  { value: 'left', label: '靠左' },
  { value: 'right', label: '靠右' },
]

export const ANIM_DIR_OPTIONS: { value: AnimDirOption; label: string }[] = [
  { value: 'left', label: '從左' },
  { value: 'right', label: '從右' },
]

export const BADGE_FILTER_OPTIONS: { value: BadgeFilterOption; label: string; desc?: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'role-sub', label: '角色+訂閱' },
  { value: 'none', label: '隱藏' },
]

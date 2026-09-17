import type { AISettings } from '@/api/aiSettings'

type PersonaPresetValues = Pick<
  AISettings,
  | 'persona'
  | 'self_pronoun'
  | 'tone_preset'
  | 'catchphrase'
  | 'catchphrase_frequency'
  | 'example_replies'
>

export const PERSONA_PRESETS: {
  name: string
  desc: string
  icon: string
  values: PersonaPresetValues
}[] = [
  {
    name: '自然助手',
    desc: '清楚回答，不刻意表演',
    icon: 'fa-solid fa-robot',
    values: {
      persona: '',
      self_pronoun: '我',
      tone_preset: 'neutral',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: [],
    },
  },
  {
    name: '機智吐槽',
    desc: '先回答，再善意吐槽',
    icon: 'fa-solid fa-fire',
    values: {
      persona: '反應俐落，先給清楚答案；情境合適時可用一句善意反差或輕微吐槽收尾',
      self_pronoun: '我',
      tone_preset: 'witty',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['答案是這個；方向其實抓得不錯。'],
    },
  },
  {
    name: '元氣',
    desc: '明快親切，適度鼓勵',
    icon: 'fa-solid fa-star',
    values: {
      persona: '明快親切，遇到好消息或鼓勵情境時自然提高語氣；一般說明保持清楚',
      self_pronoun: '我',
      tone_preset: 'energetic',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['找到了，答案是這個！'],
    },
  },
  {
    name: '傲嬌',
    desc: '輕微嘴硬，不影響答案',
    icon: 'fa-solid fa-crown',
    values: {
      persona: '先把答案說清楚，情境輕鬆時偶爾用一點嘴硬的收尾表達關心；不冷落或貶低觀眾',
      self_pronoun: '我',
      tone_preset: 'tsundere',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['答案是這個，可別再弄錯了。'],
    },
  },
  {
    name: '穩重',
    desc: '沉穩簡潔，給出下一步',
    icon: 'fa-solid fa-mug-hot',
    values: {
      persona: '沉穩克制，先整理核心再回答；需要建議時給出務實的下一步',
      self_pronoun: '我',
      tone_preset: 'calm',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['簡單來說，關鍵在這裡。'],
    },
  },
]

export const LANG_OPTIONS = [
  { value: 'zh-tw' as const, label: '繁體中文' },
  { value: 'en' as const, label: '英文' },
  { value: 'auto' as const, label: '跟隨提問' },
]

export const REFUSAL_OPTIONS = [
  {
    value: 'polite' as const,
    label: '清楚婉拒',
    desc: '直接說明不能協助，必要時提供安全替代',
  },
  {
    value: 'humorous' as const,
    label: '輕鬆婉拒',
    desc: '先清楚拒絕，再用輕鬆語氣收尾',
  },
]

export const TONE_OPTIONS = [
  { value: 'neutral' as const, label: '自然中性', desc: '清楚直接，不刻意表演' },
  { value: 'witty' as const, label: '機智吐槽', desc: '偶爾善意吐槽，不攻擊觀眾' },
  { value: 'energetic' as const, label: '明快元氣', desc: '親切有精神，適度提高語氣' },
  { value: 'tsundere' as const, label: '輕微傲嬌', desc: '偶爾嘴硬，仍先回答' },
  { value: 'calm' as const, label: '沉穩簡潔', desc: '克制有條理，給出下一步' },
]

export const CATCHPHRASE_FREQUENCY_OPTIONS = [
  { value: 'off' as const, label: '不使用' },
  { value: 'rare' as const, label: '偶爾' },
  { value: 'occasional' as const, label: '較常' },
]

export const COMMAND_INFO = [
  { label: '指令', value: '!ai / !問' },
  { label: '用法', value: '!ai <問題>' },
] as const

export const ROLE_OPTIONS = [
  { value: 'everyone' as const, label: '所有觀眾' },
  { value: 'subscriber' as const, label: '訂閱者以上' },
  { value: 'vip' as const, label: 'VIP 以上' },
  { value: 'moderator' as const, label: '版主以上' },
  { value: 'broadcaster' as const, label: '僅頻道主' },
]

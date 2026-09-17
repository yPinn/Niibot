import type { AISettings } from '@/api/aiSettings'

type PersonaPresetValues = Pick<
  AISettings,
  | 'persona'
  | 'self_pronoun'
  | 'tone_preset'
  | 'catchphrase'
  | 'catchphrase_frequency'
  | 'example_replies'
  | 'refusal_style'
>

export const PERSONA_PRESETS: {
  name: string
  desc: string
  icon: string
  values: PersonaPresetValues
}[] = [
  {
    name: '預設',
    desc: '中性助手',
    icon: 'fa-solid fa-robot',
    values: {
      persona: '',
      self_pronoun: '我',
      tone_preset: 'neutral',
      catchphrase: '',
      catchphrase_frequency: 'rare',
      example_replies: [],
      refusal_style: 'humorous',
    },
  },
  {
    name: '機智吐槽',
    desc: '反應俐落，偶爾善意吐槽',
    icon: 'fa-solid fa-fire',
    values: {
      persona: '反應俐落，先給清楚答案；情境合適時可用一句善意反差或輕微吐槽收尾',
      self_pronoun: '我',
      tone_preset: 'witty',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['答案是這個；方向其實抓得不錯。'],
      refusal_style: 'humorous',
    },
  },
  {
    name: '元氣',
    desc: '活潑開朗，充滿熱情',
    icon: 'fa-solid fa-star',
    values: {
      persona: '明快親切，遇到好消息或鼓勵情境時自然提高語氣；一般說明保持清楚',
      self_pronoun: '我',
      tone_preset: 'energetic',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['找到了，答案是這個！'],
      refusal_style: 'polite',
    },
  },
  {
    name: '傲嬌',
    desc: '嘴硬心軟，認真本質',
    icon: 'fa-solid fa-crown',
    values: {
      persona: '先把答案說清楚，情境輕鬆時偶爾用一點嘴硬的收尾表達關心；不冷落或貶低觀眾',
      self_pronoun: '我',
      tone_preset: 'tsundere',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['答案是這個，可別再弄錯了。'],
      refusal_style: 'humorous',
    },
  },
  {
    name: '穩重',
    desc: '見多識廣，語帶智慧',
    icon: 'fa-solid fa-mug-hot',
    values: {
      persona: '沉穩克制，先整理核心再回答；需要建議時給出務實的下一步',
      self_pronoun: '我',
      tone_preset: 'calm',
      catchphrase: '',
      catchphrase_frequency: 'off',
      example_replies: ['簡單來說，關鍵在這裡。'],
      refusal_style: 'humorous',
    },
  },
]

export const LANG_OPTIONS = [
  { value: 'zh-tw' as const, label: '繁中' },
  { value: 'en' as const, label: '英文' },
  { value: 'auto' as const, label: '自動' },
]

export const REFUSAL_OPTIONS = [
  { value: 'humorous' as const, label: '冷幽默', desc: '假裝系統錯誤、腦袋當機' },
  { value: 'polite' as const, label: '禮貌拒絕', desc: '直接說無法協助' },
]

export const TONE_OPTIONS = [
  { value: 'neutral' as const, label: '自然', desc: '中性、清楚、不刻意表演' },
  { value: 'witty' as const, label: '機智', desc: '善意吐槽，不攻擊觀眾' },
  { value: 'energetic' as const, label: '元氣', desc: '活潑、有精神' },
  { value: 'tsundere' as const, label: '傲嬌', desc: '嘴硬心軟，仍認真回答' },
  { value: 'calm' as const, label: '沉穩', desc: '克制、簡潔、有餘裕' },
]

export const CATCHPHRASE_FREQUENCY_OPTIONS = [
  { value: 'off' as const, label: '不用' },
  { value: 'rare' as const, label: '少量' },
  { value: 'occasional' as const, label: '較常（不連續）' },
]

export const COMMAND_INFO = [
  { label: '指令', value: '!ai / !問' },
  { label: '用法', value: '!ai <問題>' },
] as const

export const ROLE_OPTIONS = [
  { value: 'everyone' as const, label: '所有人' },
  { value: 'subscriber' as const, label: '訂閱者' },
  { value: 'vip' as const, label: 'VIP' },
  { value: 'moderator' as const, label: '版主' },
  { value: 'broadcaster' as const, label: '頻道主' },
]

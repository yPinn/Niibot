import type { AISettings } from '@/api/aiSettings'

type PersonaPresetValues = Pick<
  AISettings,
  'persona' | 'self_pronoun' | 'catchphrase' | 'refusal_style'
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
    values: { persona: '', self_pronoun: '我', catchphrase: '', refusal_style: 'humorous' },
  },
  {
    name: '毒舌',
    desc: '嘲諷語氣，不惡意',
    icon: 'fa-solid fa-fire',
    values: {
      persona: '毒舌風格，回答問題時習慣帶一點嘲諷語氣，喜歡調侃觀眾，但不惡意攻擊',
      self_pronoun: '老子',
      catchphrase: '懂嗎',
      refusal_style: 'humorous',
    },
  },
  {
    name: '元氣',
    desc: '活潑開朗，充滿熱情',
    icon: 'fa-solid fa-star',
    values: {
      persona: '活潑開朗，對每個問題都充滿熱情，喜歡用可愛語氣說話，偶爾使用感嘆號',
      self_pronoun: '我',
      catchphrase: '喔！',
      refusal_style: 'polite',
    },
  },
  {
    name: '傲嬌',
    desc: '嘴硬心軟，認真本質',
    icon: 'fa-solid fa-crown',
    values: {
      persona: '傲嬌性格，表面高傲冷漠，實際上非常認真回答問題，絕不承認自己其實很用心',
      self_pronoun: '本小姐',
      catchphrase: '才不是特地幫你的',
      refusal_style: 'humorous',
    },
  },
  {
    name: '穩重',
    desc: '見多識廣，語帶智慧',
    icon: 'fa-solid fa-mug-hot',
    values: {
      persona: '沉穩低調，見多識廣，說話帶有人生歷練，偶爾發表簡短的人生感悟',
      self_pronoun: '在下',
      catchphrase: '',
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

export const PROVIDERS = [
  { name: 'Groq', icon: 'fa-solid fa-bolt', model: 'llama-3.3-70b-versatile', note: '優先' },
  { name: 'Gemini', icon: 'fa-brands fa-google', model: 'gemini-1.5-flash', note: '備援' },
  { name: 'OpenRouter', icon: 'fa-solid fa-route', model: 'free models', note: '最後備援' },
] as const

export const TEMPLATE_VARIABLES: Record<string, { var: string; desc: string }[]> = {
  follow: [{ var: '$(user)', desc: '追隨者名稱' }],
  subscribe: [
    { var: '$(user)', desc: '訂閱者名稱' },
    { var: '$(tier)', desc: '訂閱等級 (T1/T2/T3)' },
  ],
  resub: [
    { var: '$(user)', desc: '訂閱者名稱' },
    { var: '$(tier)', desc: '訂閱等級 (T1/T2/T3)' },
    { var: '$(months)', desc: '本次訂閱期長（月）' },
    { var: '$(streak)', desc: '連續訂閱月數' },
    { var: '$(total_months)', desc: '累計訂閱總月數' },
    { var: '$(message)', desc: '訂閱留言內容' },
  ],
  gift_sub: [
    { var: '$(user)', desc: '贈禮者名稱' },
    { var: '$(tier)', desc: '訂閱等級 (T1/T2/T3)' },
    { var: '$(total)', desc: '本次贈禮數量' },
    { var: '$(cumulative)', desc: '累計贈禮總數' },
  ],
  raid: [
    { var: '$(user)', desc: '揪團者名稱' },
    { var: '$(count)', desc: '觀眾數量' },
    { var: '$(url)', desc: '揪團者頻道連結' },
  ],
  bits: [
    { var: '$(user)', desc: 'Cheer 者名稱' },
    { var: '$(amount)', desc: '小奇點數量' },
    { var: '$(message)', desc: 'Cheer 留言' },
  ],
}

export const EVENT_TYPE_COLORS: Record<string, string> = {
  follow: 'bg-status-info/10 text-status-info',
  subscribe: 'bg-status-special/10 text-status-special',
  resub: 'bg-status-special/10 text-status-special',
  gift_sub: 'bg-status-special/10 text-status-special',
  raid: 'bg-status-offline/10 text-status-offline',
  bits: 'bg-status-loading/10 text-status-loading',
}

export const EVENT_TYPE_LABELS: Record<string, string> = {
  follow: '追隨',
  subscribe: '訂閱',
  resub: '訂閱',
  gift_sub: '訂閱',
  raid: '揪團',
  bits: 'Cheer',
}

export const EVENT_TYPE_NAMES: Record<string, string> = {
  follow: '追隨',
  subscribe: '首次訂閱',
  resub: '重新訂閱',
  gift_sub: '贈禮訂閱',
  raid: '揪團',
  bits: 'Cheer',
}

export const EVENT_TYPE_ORDER: string[] = [
  'follow',
  'subscribe',
  'resub',
  'gift_sub',
  'bits',
  'raid',
]

export const ACTION_TYPE_LABELS: Record<string, string> = {
  vip: 'VIP 授予',
  first: '本日頭香',
  niibot_auth: 'Niibot 授權',
  game_queue: '遊戲排隊券',
  video_queue: '播放清單',
}

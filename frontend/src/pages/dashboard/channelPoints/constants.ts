export const ACTION_TYPE_LABELS: Record<string, string> = {
  vip: 'VIP 授予',
  first: '本日頭香',
  game_queue: '遊戲排隊券',
  video_queue: '播放清單',
  checkin: '每日簽到',
}

export const ACTION_TYPE_DEFAULT_ORDER = [
  'first',
  'game_queue',
  'video_queue',
  'checkin',
  'vip',
] as const

export const ACTION_TYPE_DESCRIPTIONS: Record<string, string> = {
  vip: '兌換後由 Niibot 授予 VIP。',
  first: '記錄當日第一位完成兌換的觀眾。',
  game_queue: '將觀眾加入 Game Queue。',
  video_queue: '將觀眾輸入的影片加入 Video Queue。',
  checkin: '與聊天指令共用每日簽到紀錄，成功時可顯示 Community Overlay。',
}

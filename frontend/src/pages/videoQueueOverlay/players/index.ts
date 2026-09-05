import { bilibiliStrategy } from './bilibili'
import { twitchClipStrategy } from './twitchClip'
import type { PlayerStrategy } from './types'
import { youtubeStrategy } from './youtube'

const STRATEGIES: Record<string, PlayerStrategy> = {
  youtube: youtubeStrategy,
  twitch_clip: twitchClipStrategy,
  bilibili: bilibiliStrategy,
}

export function getPlayerStrategy(videoType: string): PlayerStrategy | undefined {
  return STRATEGIES[videoType]
}

export { destroyAllPlayers } from './shared'
export { loadTwitchEmbedAPI } from './twitchClip'
export type { MountContext, PlayerStrategy, TwitchEmbedInstance, YTPlayer } from './types'
export { loadYouTubeAPI } from './youtube'

import { describe, expect, it } from 'vitest'

import { isApiContainer } from './logParsers'

describe('isApiContainer', () => {
  it.each(['niibot-dev-api-1', 'niibot-stg-api-1', 'niibot-prod-api-1'])(
    'accepts Compose API container %s',
    name => {
      expect(isApiContainer(name)).toBe(true)
    }
  )

  it.each(['niibot-prod-twitch-bot-1', 'api', 'nb-api'])('rejects %s', name => {
    expect(isApiContainer(name)).toBe(false)
  })
})

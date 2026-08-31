import { describe, expect, it } from 'vitest'

import { discordNavigationData, navigationData } from './navigation'

describe('Twitch navigation', () => {
  it('orders primary groups by operating frequency and keeps low-frequency areas last', () => {
    expect(navigationData.navMain.map(group => group.title)).toEqual([
      'Dashboard',
      'Live Tools',
      'Analytics',
      'Modules',
      'Docs',
      'Admin',
    ])
  })

  it('orders dashboard actions from frequent interaction to background automation', () => {
    const dashboard = navigationData.navMain.find(group => group.title === 'Dashboard')

    expect(dashboard?.items).toEqual([
      { title: 'Overview', url: '/dashboard' },
      { title: 'Commands', url: '/commands' },
      { title: 'Channel Points', url: '/channel-points' },
      { title: 'Events', url: '/events' },
      { title: 'Timers', url: '/timers' },
    ])
  })

  it('groups live operations under a concise task-oriented name', () => {
    const liveTools = navigationData.navMain.find(group => group.title === 'Live Tools')

    expect(liveTools?.items).toEqual([
      { title: 'Game Queue', url: '/modules/game-queue' },
      { title: 'Video Queue', url: '/modules/video-queue' },
      { title: 'Live Display', url: '/modules/live-display' },
    ])
  })

  it('preserves owner-only admin access and Discord navigation', () => {
    expect(navigationData.navMain.at(-1)).toMatchObject({ title: 'Admin', ownerOnly: true })
    expect(discordNavigationData.navMain.map(group => group.title)).toEqual([
      'Dashboard',
      'Docs',
      'Admin',
    ])
  })
})

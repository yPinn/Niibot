export interface NavSubItem {
  title: string
  url: string
}

export interface NavGroup {
  title: string
  url: string
  icon: string
  isActive?: boolean
  ownerOnly?: boolean
  items?: NavSubItem[]
}

export interface NavSecondaryItem {
  title: string
  url: string
  icon: string
  internal?: boolean
}

export interface NavigationData {
  navMain: NavGroup[]
  navSecondary: NavSecondaryItem[]
}

// Twitch Bot 導航
export const navigationData: NavigationData = {
  navMain: [
    {
      title: 'Dashboard',
      url: '#',
      icon: 'fa-solid fa-home',
      isActive: true,
      items: [
        {
          title: 'Overview',
          url: '/dashboard',
        },
        {
          title: 'Commands',
          url: '/commands',
        },
        {
          title: 'Channel Points',
          url: '/channel-points',
        },
        {
          title: 'Events',
          url: '/events',
        },
        {
          title: 'Timers',
          url: '/timers',
        },
      ],
    },
    {
      title: 'Live Tools',
      url: '#',
      icon: 'fa-solid fa-clapperboard',
      items: [
        {
          title: 'Game Queue',
          url: '/modules/game-queue',
        },
        {
          title: 'Video Queue',
          url: '/modules/video-queue',
        },
        {
          title: 'Live Display',
          url: '/modules/live-display',
        },
      ],
    },
    {
      title: 'Analytics',
      url: '#',
      icon: 'fa-solid fa-chart-mixed',
      items: [
        {
          title: 'Insights',
          url: '/analytics/insights',
        },
        {
          title: 'Matcher',
          url: '/analytics/matcher',
        },
      ],
    },
    {
      title: 'Modules',
      url: '#',
      icon: 'fa-solid fa-puzzle-piece',
      items: [
        {
          title: 'AI Assistant',
          url: '/modules/ai',
        },
        {
          title: 'Crosshair Repo',
          url: '/modules/crosshairs',
        },
        {
          title: 'Stream Schedule',
          url: '/modules/stream-schedule',
        },
      ],
    },
    {
      title: 'Docs',
      url: '#',
      icon: 'fa-solid fa-book',
      items: [
        {
          title: 'Get Started',
          url: '/docs/get-started',
        },
        {
          title: 'Releases',
          url: '/docs/releases',
        },
        {
          title: 'Discord Bot',
          url: '/discord',
        },
      ],
    },
    {
      title: 'Admin',
      url: '#',
      icon: 'fa-solid fa-shield-halved',
      ownerOnly: true,
      items: [
        { title: 'Overview', url: '/admin' },
        { title: 'Monitor', url: '/admin/monitor' },
        { title: 'Modules', url: '/admin/modules' },
      ],
    },
  ],
  navSecondary: [
    {
      title: 'Support',
      url: '/support',
      icon: 'fa-solid fa-mug-hot',
      internal: true,
    },
    {
      title: 'Discord',
      url: import.meta.env.VITE_DISCORD_COMMUNITY_URL,
      icon: 'fa-brands fa-discord',
    },
  ],
}

// Discord Bot 導航
export const discordNavigationData: NavigationData = {
  navMain: [
    {
      title: 'Dashboard',
      url: '#',
      icon: 'fa-solid fa-home',
      isActive: true,
      items: [
        {
          title: 'Overview',
          url: '/discord',
        },
      ],
    },
    {
      title: 'Docs',
      url: '#',
      icon: 'fa-solid fa-book',
      items: [
        {
          title: 'Get Started',
          url: '/docs/get-started',
        },
        {
          title: 'Releases',
          url: '/docs/releases',
        },
      ],
    },
    {
      title: 'Admin',
      url: '#',
      icon: 'fa-solid fa-shield-halved',
      ownerOnly: true,
      items: [
        { title: 'Overview', url: '/admin' },
        { title: 'Monitor', url: '/admin/monitor' },
        { title: 'Modules', url: '/admin/modules' },
      ],
    },
  ],
  navSecondary: [
    {
      title: 'Support',
      url: '/support',
      icon: 'fa-solid fa-mug-hot',
      internal: true,
    },
    {
      title: 'Discord',
      url: import.meta.env.VITE_DISCORD_COMMUNITY_URL,
      icon: 'fa-brands fa-discord',
    },
  ],
}

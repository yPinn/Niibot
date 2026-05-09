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
          title: 'Timers',
          url: '/timers',
        },
        {
          title: 'Events',
          url: '/events',
        },
      ],
    },
    {
      title: 'Modules',
      url: '#',
      icon: 'fa-solid fa-puzzle-piece',
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
          title: 'Chat Overlay',
          url: '/modules/chat-overlay',
        },
        {
          title: 'Crosshair Repo',
          url: '/modules/crosshairs',
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
      ],
    },
    {
      title: 'Documentations',
      url: '#',
      icon: 'fa-solid fa-book',
      items: [
        {
          title: 'Get Started',
          url: '/docs/get-started',
        },
        {
          title: 'Discord Bot',
          url: '/discord/dashboard',
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
        { title: 'System Status', url: '/admin/status' },
        { title: 'Activation Codes', url: '/admin/codes' },
      ],
    },
  ],
  navSecondary: [
    {
      title: 'Discord',
      url: import.meta.env.VITE_DISCORD_INVITE_URL,
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
          url: '/discord/dashboard',
        },
      ],
    },
    {
      title: 'Documentations',
      url: '#',
      icon: 'fa-solid fa-book',
      items: [
        {
          title: 'Get Started',
          url: '/docs/get-started',
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
        { title: 'System Status', url: '/admin/status' },
        { title: 'Activation Codes', url: '/admin/codes' },
      ],
    },
  ],
  navSecondary: [
    {
      title: 'Discord',
      url: import.meta.env.VITE_DISCORD_INVITE_URL,
      icon: 'fa-brands fa-discord',
    },
  ],
}

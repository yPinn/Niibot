// Twitch Bot 導航
export const navigationData = {
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
      ],
    },
    {
      title: 'Analytics',
      url: '#',
      icon: 'fa-solid fa-chart-mixed',
      items: [
        {
          title: 'Insights',
          url: '/insights',
        },
        {
          title: 'System Status',
          url: '/system',
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
          url: '/docs',
        },
        {
          title: 'Discord Bot',
          url: '/discord/dashboard',
        },
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
export const discordNavigationData = {
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
        {
          title: 'System Status',
          url: '/system',
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
          url: '/docs',
        },
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

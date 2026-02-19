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
          title: 'Events',
          url: '/events',
        },
        {
          title: 'System Status',
          url: '/system',
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
          url: '/analytics',
        },
        {
          title: 'Leaderboard',
          url: '/analytics/leaderboard',
        },
      ],
    },
    {
      title: 'Modules',
      url: '#',
      icon: 'fa-solid fa-puzzle-piece',
      items: [
        {
          title: 'Giveaways',
          url: '/modules/giveaways',
        },
        {
          title: 'Game Queue',
          url: '/modules/game-queue',
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
          url: '/discord',
        },
      ],
    },
  ],
  navSecondary: [
    {
      title: 'Github',
      url: 'https://github.com/yPinn/Niibot',
      icon: 'fa-brands fa-github',
    },
    {
      title: 'Discord',
      url: 'https://discord.gg/GubS4Xcb7W',
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
          title: 'Servers',
          url: '/discord/servers',
        },
        {
          title: 'System Status',
          url: '/system',
        },
      ],
    },
    {
      title: 'Configuration',
      url: '#',
      icon: 'fa-solid fa-gear',
      items: [
        {
          title: 'Commands',
          url: '/discord/commands',
        },
        {
          title: 'Auto Responses',
          url: '/discord/auto-responses',
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
          url: '/discord/docs',
        },
      ],
    },
  ],
  navSecondary: [
    {
      title: 'Github',
      url: '#',
      icon: 'fa-brands fa-github',
    },
    {
      title: 'Twitch',
      url: 'https://twitch.tv',
      icon: 'fa-brands fa-twitch',
    },
  ],
}

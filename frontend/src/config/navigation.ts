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
      url: '#',
      icon: 'fa-brands fa-github',
    },
    {
      title: 'Discord',
      url: 'https://discord.gg/GubS4Xcb7W',
      icon: 'fa-brands fa-discord',
    },
  ],
}

/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  // Community/support server invite — sidebar, help banner, Terms/Privacy contact.
  readonly VITE_DISCORD_COMMUNITY_URL: string
  // Discord Install Link — adds the Niibot bot to the user's own server.
  readonly VITE_DISCORD_BOT_INVITE_URL: string
  // Deployment target ('production' | 'staging'); unset in local dev.
  readonly VITE_ENVIRONMENT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

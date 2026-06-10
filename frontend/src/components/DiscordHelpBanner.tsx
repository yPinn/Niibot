import { Icon } from '@/components/primitives'

const INVITE_URL = import.meta.env.VITE_DISCORD_INVITE_URL

export function DiscordHelpBanner() {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-muted/30 px-page py-3">
      <Icon icon="fa-brands fa-discord" size="lg" wrapperClassName="text-discord" />
      <p className="text-sub">
        <span className="font-medium">遇到問題？</span>
        <span className="ml-1 text-muted-foreground">
          加入{' '}
          <a
            href={INVITE_URL}
            target="_blank"
            rel="noreferrer"
            className="text-primary underline-offset-4 hover:underline"
          >
            Discord 社群
          </a>{' '}
          回報問題或提出建議。
        </span>
      </p>
    </div>
  )
}
